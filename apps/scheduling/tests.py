from datetime import date, time, datetime, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clinical.models import Patient
from apps.organizations.models import (
    Department,
    DoctorProfile,
    Hospital,
    OperatingRoom,
    Organization,
    StaffProfile,
)
from .models import (
    Appointment,
    DoctorSchedule,
    ExceptionalWorkingDay,
    OperatingRoomSchedule,
    TimeOff,
    WorkingHours,
)


class SchedulingModelsTests(TestCase):
    def setUp(self):
        # 1. Organization & Hospital
        self.org = Organization.objects.create(
            name="Metro Health",
            legal_name="Metro Health LLC",
            tax_id="TAX-MTR-1",
            address="50 Metro Blvd",
            email="metro@health.com",
            phone_number="+998901119901",
        )
        self.hospital = Hospital.objects.create(
            organization=self.org,
            name="Metro Central",
            code="MC-01",
            address="50 Metro Blvd",
            city="Tashkent",
            phone_number="+998901119902",
            email="mc@metro.com",
        )
        self.department = Department.objects.create(
            hospital=self.hospital,
            name="General Surgery",
            code="GSURG",
        )

        # 2. Doctor
        self.doctor_user = User.objects.create_user(
            email="dr.strange@metro.com",
            phone_number="+998901119903",
            full_name="Stephen Strange",
            password="StrongPassword123!",
            role=User.Role.DOCTOR,
            is_active=True,
        )
        self.staff_profile = StaffProfile.objects.create(
            user=self.doctor_user,
            organization=self.org,
            hospital=self.hospital,
            department=self.department,
            employee_id="SURG-001",
            hire_date=date(2024, 1, 1),
        )
        self.doctor = DoctorProfile.objects.create(
            staff_profile=self.staff_profile,
            specialization="Neurosurgeon",
            years_of_experience=12,
            consultation_fee=Decimal("200.00"),
            license_number="LIC-STRANGE-1",
            license_expiry_date=date(2030, 1, 1),
        )

        # 3. Patient
        self.patient = Patient.objects.create(
            first_name="Peter",
            last_name="Parker",
            dob=date(2001, 8, 10),
            gender=Patient.Gender.MALE,
            blood_type=Patient.BloodType.O_POS,
            phone_number="+998901119904",
            organization=self.org,
            primary_hospital=self.hospital,
        )

        # 4. Operating Room
        self.operating_room = OperatingRoom.objects.create(
            hospital=self.hospital,
            department=self.department,
            name="Surgical Suite 1",
            code="OR-S1",
            specialty="Neurosurgery",
            status=OperatingRoom.ORStatus.AVAILABLE,
        )

    def test_doctor_schedule_and_working_hours(self):
        schedule = DoctorSchedule.objects.create(
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            slot_duration_minutes=30,
        )
        self.assertTrue(str(schedule).startswith("Schedule: Dr. Stephen Strange"))

        # Working Hours on Monday from 09:00 to 17:00
        working_hours = WorkingHours.objects.create(
            doctor_schedule=schedule,
            day_of_week=WorkingHours.DayOfWeek.MONDAY,
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        self.assertEqual(str(working_hours), "Monday: 09:00 - 17:00")

        # Invalid working hours: end_time <= start_time
        invalid_hours = WorkingHours(
            doctor_schedule=schedule,
            day_of_week=WorkingHours.DayOfWeek.TUESDAY,
            start_time=time(15, 0),
            end_time=time(14, 0),
        )
        with self.assertRaises(ValidationError):
            invalid_hours.clean()

        # Overlapping shift on the same day must fail
        overlapping_shift = WorkingHours(
            doctor_schedule=schedule,
            day_of_week=WorkingHours.DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        with self.assertRaises(ValidationError):
            overlapping_shift.clean()

    def test_exceptional_working_day_validation(self):
        schedule = DoctorSchedule.objects.create(
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            slot_duration_minutes=30,
        )

        # 1. Working day requires start and end time
        invalid_day = ExceptionalWorkingDay(
            doctor_schedule=schedule,
            date=date(2026, 12, 25),
            is_working_day=True,
            start_time=None,
            end_time=None,
        )
        with self.assertRaises(ValidationError):
            invalid_day.clean()

        # 2. End time must be after start time
        invalid_times = ExceptionalWorkingDay(
            doctor_schedule=schedule,
            date=date(2026, 12, 25),
            is_working_day=True,
            start_time=time(14, 0),
            end_time=time(12, 0),
        )
        with self.assertRaises(ValidationError):
            invalid_times.clean()

        # 3. Valid exceptional working day
        exp1 = ExceptionalWorkingDay.objects.create(
            doctor_schedule=schedule,
            date=date(2026, 12, 25),
            is_working_day=True,
            start_time=time(9, 0),
            end_time=time(13, 0),
            reason="Holiday on-call",
        )
        self.assertIn("09:00 - 13:00", str(exp1))

        # 4. Overlapping shift on the same date must fail
        exp_overlap = ExceptionalWorkingDay(
            doctor_schedule=schedule,
            date=date(2026, 12, 25),
            is_working_day=True,
            start_time=time(11, 0),
            end_time=time(14, 0),
        )
        with self.assertRaises(ValidationError):
            exp_overlap.clean()

        # 5. Off-day override
        exp_off = ExceptionalWorkingDay.objects.create(
            doctor_schedule=schedule,
            date=date(2026, 12, 26),
            is_working_day=False,
            reason="Clinic closed",
        )
        self.assertIn("Off-day override", str(exp_off))

    def test_appointment_working_hours_and_exceptional_days(self):
        schedule = DoctorSchedule.objects.create(
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            slot_duration_minutes=30,
        )
        # Monday working hours: 09:00 to 17:00
        WorkingHours.objects.create(
            doctor_schedule=schedule,
            day_of_week=WorkingHours.DayOfWeek.MONDAY,
            start_time=time(9, 0),
            end_time=time(17, 0),
        )

        # Find next Monday and next Sunday
        today = date.today()
        days_until_next_monday = (0 - today.weekday() + 7) % 7 or 7
        next_monday = today + timedelta(days=days_until_next_monday)
        next_sunday = next_monday + timedelta(days=6)

        # 1. Booking within Monday working hours succeeds
        appt_valid = Appointment(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=timezone.make_aware(datetime.combine(next_monday, time(10, 0))),
            end_time=timezone.make_aware(datetime.combine(next_monday, time(10, 30))),
            reason="Monday Checkup",
        )
        appt_valid.clean()
        appt_valid.save()
        self.assertIsNotNone(appt_valid.pk)

        # 2. Booking outside Monday working hours fails (18:00 - 18:30)
        appt_outside_hours = Appointment(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=timezone.make_aware(datetime.combine(next_monday, time(18, 0))),
            end_time=timezone.make_aware(datetime.combine(next_monday, time(18, 30))),
            reason="Late visit",
        )
        with self.assertRaises(ValidationError) as ctx:
            appt_outside_hours.clean()
        self.assertIn("outside Dr. Stephen Strange's scheduled working hours", str(ctx.exception))

        # 3. Booking on Sunday (no scheduled hours) fails
        appt_sunday = Appointment(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=timezone.make_aware(datetime.combine(next_sunday, time(10, 0))),
            end_time=timezone.make_aware(datetime.combine(next_sunday, time(10, 30))),
            reason="Sunday visit",
        )
        with self.assertRaises(ValidationError) as ctx:
            appt_sunday.clean()
        self.assertIn("does not have scheduled working hours on Sunday", str(ctx.exception))

        # 4. Add Exceptional Working Day for Sunday (on-call: 10:00 - 14:00)
        ExceptionalWorkingDay.objects.create(
            doctor_schedule=schedule,
            date=next_sunday,
            start_time=time(10, 0),
            end_time=time(14, 0),
            is_working_day=True,
            reason="Sunday on-call shift",
        )
        # Now Sunday booking within on-call hours succeeds
        appt_sunday.clean()
        appt_sunday.save()
        self.assertIsNotNone(appt_sunday.pk)

        # 5. Exceptional off-day override on a working day
        following_monday = next_monday + timedelta(days=7)
        ExceptionalWorkingDay.objects.create(
            doctor_schedule=schedule,
            date=following_monday,
            is_working_day=False,
            reason="National Holiday",
        )
        appt_holiday = Appointment(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=timezone.make_aware(datetime.combine(following_monday, time(10, 0))),
            end_time=timezone.make_aware(datetime.combine(following_monday, time(10, 30))),
            reason="Holiday appointment",
        )
        with self.assertRaises(ValidationError) as ctx:
            appt_holiday.clean()
        self.assertIn("scheduled off-day override", str(ctx.exception))

    def test_doctor_time_off_validation(self):
        start = timezone.now() + timedelta(days=5)
        end = start + timedelta(days=3)

        time_off = TimeOff.objects.create(
            doctor=self.doctor,
            start_datetime=start,
            end_datetime=end,
            leave_type=TimeOff.LeaveType.VACATION,
            status=TimeOff.Status.APPROVED,
            reason="Annual leave",
        )
        self.assertIn("Leave", str(time_off))

        # Invalid: end before start
        invalid_leave = TimeOff(
            doctor=self.doctor,
            start_datetime=end,
            end_datetime=start,
        )
        with self.assertRaises(ValidationError):
            invalid_leave.clean()

    def test_appointment_booking_and_conflict_prevention(self):
        base_time = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1, hours=10)
        start1 = base_time
        end1 = base_time + timedelta(minutes=30)

        # 1. Create first appointment
        appt1 = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=start1,
            end_time=end1,
            status=Appointment.Status.SCHEDULED,
            reason="Headache consultation",
        )
        self.assertEqual(appt1.status, Appointment.Status.SCHEDULED)
        self.assertIn("Peter Parker with Dr. Stephen Strange", str(appt1))

        # 2. Overlapping appointment for the same doctor must fail conflict prevention
        overlap_start = base_time + timedelta(minutes=15)
        overlap_end = overlap_start + timedelta(minutes=30)
        conflict_appt = Appointment(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=overlap_start,
            end_time=overlap_end,
            reason="Follow-up check",
        )
        with self.assertRaises(ValidationError) as ctx:
            conflict_appt.clean()
        self.assertIn("Conflict: Dr. Stephen Strange already has an active appointment", str(ctx.exception))

        # 3. If first appointment is cancelled, booking the same slot is allowed
        appt1.status = Appointment.Status.CANCELLED
        appt1.save()

        replacement_appt = Appointment(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=start1,
            end_time=end1,
            reason="Slot re-booked",
        )
        # Should not raise any conflict error
        replacement_appt.clean()
        replacement_appt.save()
        self.assertIsNotNone(replacement_appt.pk)

    def test_appointment_blocked_during_approved_doctor_time_off(self):
        vacation_start = timezone.now() + timedelta(days=7)
        vacation_end = vacation_start + timedelta(days=5)

        TimeOff.objects.create(
            doctor=self.doctor,
            start_datetime=vacation_start,
            end_datetime=vacation_end,
            status=TimeOff.Status.APPROVED,
            leave_type=TimeOff.LeaveType.CONFERENCE,
        )

        # Attempt to book an appointment during the conference
        appt_during_leave = Appointment(
            patient=self.patient,
            doctor=self.doctor,
            hospital=self.hospital,
            department=self.department,
            start_time=vacation_start + timedelta(hours=2),
            end_time=vacation_start + timedelta(hours=3),
            reason="Consultation during leave",
        )
        with self.assertRaises(ValidationError) as ctx:
            appt_during_leave.clean()
        self.assertIn("is on approved Conference / Training", str(ctx.exception))

    def test_operating_room_schedule_and_double_booking_prevention(self):
        surgery_start = timezone.now() + timedelta(days=2, hours=8)
        surgery_end = surgery_start + timedelta(hours=3)

        or_schedule1 = OperatingRoomSchedule.objects.create(
            operating_room=self.operating_room,
            patient=self.patient,
            lead_surgeon=self.doctor,
            procedure_name="Craniotomy",
            start_time=surgery_start,
            end_time=surgery_end,
            status=OperatingRoomSchedule.Status.RESERVED,
        )
        self.assertIn("Craniotomy in Surgical Suite 1", str(or_schedule1))

        # Attempt to book the same OR suite during overlapping hours
        conflict_or = OperatingRoomSchedule(
            operating_room=self.operating_room,
            patient=self.patient,
            lead_surgeon=self.doctor,
            procedure_name="Emergency Neuro Procedure",
            start_time=surgery_start + timedelta(hours=1),
            end_time=surgery_end + timedelta(hours=1),
        )
        with self.assertRaises(ValidationError) as ctx:
            conflict_or.clean()
        self.assertIn("is already reserved for 'Craniotomy'", str(ctx.exception))


class SchedulingAPITests(APITestCase):
    def setUp(self):
        self.password = "StrongPassword123!"

        # Organization 1 & Hospital 1
        self.org1 = Organization.objects.create(
            name="Alpha Health", legal_name="Alpha Health LLC", tax_id="TAX-A1",
            address="1 Alpha Way", email="alpha@health.com", phone_number="+998901000001",
        )
        self.hosp1 = Hospital.objects.create(
            organization=self.org1, name="Alpha Clinic", code="AC-01",
            address="1 Alpha Way", city="Tashkent", phone_number="+998901000002", email="ac@alpha.com",
        )
        self.dept1 = Department.objects.create(
            hospital=self.hosp1, name="Cardiology", code="CARD",
        )

        # Organization 2 (Tenant scoping)
        self.org2 = Organization.objects.create(
            name="Beta Health", legal_name="Beta Health LLC", tax_id="TAX-B1",
            address="2 Beta Way", email="beta@health.com", phone_number="+998901000003",
        )
        self.hosp2 = Hospital.objects.create(
            organization=self.org2, name="Beta Clinic", code="BC-01",
            address="2 Beta Way", city="Samarkand", phone_number="+998901000004", email="bc@beta.com",
        )
        self.dept2 = Department.objects.create(
            hospital=self.hosp2, name="Cardiology South", code="CARDS",
        )

        # Doctor in Org 1
        self.doctor_user = User.objects.create_user(
            email="doc.alpha@health.com", phone_number="+998901000010", full_name="Dr. Alpha",
            password=self.password, role=User.Role.DOCTOR, is_active=True,
        )
        self.staff1 = StaffProfile.objects.create(
            user=self.doctor_user, organization=self.org1, hospital=self.hosp1,
            department=self.dept1, employee_id="DOC-A1", hire_date=date(2024, 1, 1),
        )
        self.doctor1 = DoctorProfile.objects.create(
            staff_profile=self.staff1, specialization="Cardiologist",
            years_of_experience=10, consultation_fee=Decimal("100.00"),
            license_number="LIC-ALPHA-1", license_expiry_date=date(2030, 1, 1),
        )

        # Receptionist in Org 1
        self.receptionist = User.objects.create_user(
            email="reception.alpha@health.com", phone_number="+998901000011", full_name="Receptionist Alpha",
            password=self.password, role=User.Role.RECEPTIONIST, is_active=True,
        )
        StaffProfile.objects.create(
            user=self.receptionist, organization=self.org1, hospital=self.hosp1,
            department=self.dept1, employee_id="REC-A1", hire_date=date(2024, 1, 1),
        )

        # Patient 1 in Org 1, Patient 2 in Org 2
        self.patient1 = Patient.objects.create(
            first_name="Tony", last_name="Stark", dob=date(1975, 5, 29),
            gender=Patient.Gender.MALE, blood_type=Patient.BloodType.A_POS,
            phone_number="+998901000020", organization=self.org1, primary_hospital=self.hosp1,
        )
        self.patient2 = Patient.objects.create(
            first_name="Steve", last_name="Rogers", dob=date(1920, 7, 4),
            gender=Patient.Gender.MALE, blood_type=Patient.BloodType.O_POS,
            phone_number="+998901000021", organization=self.org2, primary_hospital=self.hosp2,
        )

        # Operating Room in Hosp 1
        self.or1 = OperatingRoom.objects.create(
            hospital=self.hosp1, department=self.dept1, name="OR 1",
            code="OR-01", status=OperatingRoom.ORStatus.AVAILABLE,
        )

        # Hospital Admin in Org 1
        self.admin_user = User.objects.create_user(
            email="admin.alpha@health.com", phone_number="+998901000099", full_name="Admin Alpha",
            password=self.password, role=User.Role.ADMIN, is_active=True,
        )
        StaffProfile.objects.create(
            user=self.admin_user, organization=self.org1, hospital=self.hosp1,
            department=self.dept1, employee_id="ADM-A1", hire_date=date(2024, 1, 1),
        )

    def test_appointment_api_booking_and_conflict_rejection(self):
        self.client.force_authenticate(user=self.receptionist)
        start = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=2, hours=9)
        end = start + timedelta(minutes=30)

        # 1. Successful booking
        payload = {
            "patient": str(self.patient1.pk),
            "doctor": str(self.doctor1.pk),
            "hospital": str(self.hosp1.pk),
            "department": str(self.dept1.pk),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "reason": "Cardiac checkup",
            "appointment_type": "routine",
        }
        res = self.client.post("/api/scheduling/appointments/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "scheduled")
        appt_id = res.data["id"]

        # 2. Double-booking conflict returns 400 Bad Request
        conflict_payload = {
            "patient": str(self.patient1.pk),
            "doctor": str(self.doctor1.pk),
            "hospital": str(self.hosp1.pk),
            "department": str(self.dept1.pk),
            "start_time": (start + timedelta(minutes=15)).isoformat(),
            "end_time": (end + timedelta(minutes=15)).isoformat(),
            "reason": "Overlapping booking",
        }
        res_conflict = self.client.post("/api/scheduling/appointments/", conflict_payload, format="json")
        self.assertEqual(res_conflict.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Conflict", str(res_conflict.data))

    def test_appointment_lifecycle_state_transitions(self):
        self.client.force_authenticate(user=self.receptionist)
        start = timezone.now() + timedelta(days=3, hours=10)
        end = start + timedelta(minutes=30)

        appt = Appointment.objects.create(
            patient=self.patient1, doctor=self.doctor1,
            hospital=self.hosp1, department=self.dept1,
            start_time=start, end_time=end,
            status=Appointment.Status.SCHEDULED, reason="Routine Exam",
        )

        # 1. Confirm
        res_confirm = self.client.post(f"/api/scheduling/appointments/{appt.pk}/confirm/")
        self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)
        self.assertEqual(res_confirm.data["status"], "confirmed")

        # 2. Check-in
        res_checkin = self.client.post(f"/api/scheduling/appointments/{appt.pk}/check-in/")
        self.assertEqual(res_checkin.status_code, status.HTTP_200_OK)
        self.assertEqual(res_checkin.data["status"], "checked_in")

        # 3. Doctor starts consultation
        self.client.force_authenticate(user=self.doctor_user)
        res_start = self.client.post(f"/api/scheduling/appointments/{appt.pk}/start/")
        self.assertEqual(res_start.status_code, status.HTTP_200_OK)
        self.assertEqual(res_start.data["status"], "in_progress")

        # 4. Doctor completes consultation
        res_complete = self.client.post(f"/api/scheduling/appointments/{appt.pk}/complete/")
        self.assertEqual(res_complete.status_code, status.HTTP_200_OK)
        self.assertEqual(res_complete.data["status"], "completed")

    def test_appointment_reschedule_and_cancel_actions(self):
        self.client.force_authenticate(user=self.receptionist)
        start = timezone.now() + timedelta(days=4, hours=14)
        end = start + timedelta(minutes=30)

        appt = Appointment.objects.create(
            patient=self.patient1, doctor=self.doctor1,
            hospital=self.hosp1, department=self.dept1,
            start_time=start, end_time=end,
            status=Appointment.Status.SCHEDULED, reason="General Consultation",
        )

        # 1. Reschedule
        new_start = start + timedelta(days=1)
        new_end = end + timedelta(days=1)
        res_reschedule = self.client.post(
            f"/api/scheduling/appointments/{appt.pk}/reschedule/",
            {"new_start_time": new_start.isoformat(), "new_end_time": new_end.isoformat()},
            format="json",
        )
        self.assertEqual(res_reschedule.status_code, status.HTTP_200_OK)
        appt.refresh_from_db()
        self.assertEqual(appt.start_time, new_start)

        # 2. Cancel
        res_cancel = self.client.post(
            f"/api/scheduling/appointments/{appt.pk}/cancel/",
            {"cancellation_reason": "Patient requested cancellation due to travel"},
            format="json",
        )
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointment.Status.CANCELLED)
        self.assertEqual(appt.cancellation_reason, "Patient requested cancellation due to travel")

    def test_operating_room_schedule_api_and_conflict_handling(self):
        self.client.force_authenticate(user=self.doctor_user)
        start = timezone.now() + timedelta(days=5, hours=8)
        end = start + timedelta(hours=2)

        # 1. Reserve OR
        payload = {
            "operating_room": str(self.or1.pk),
            "patient": str(self.patient1.pk),
            "lead_surgeon": str(self.doctor1.pk),
            "procedure_name": "Angioplasty",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "status": "reserved",
        }
        res = self.client.post("/api/scheduling/operating-room-schedules/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["operating_room_name"], "OR 1")
        or_schedule_id = res.data["id"]

        # 2. Overlapping OR reservation fails with 400
        conflict_payload = {
            "operating_room": str(self.or1.pk),
            "patient": str(self.patient1.pk),
            "lead_surgeon": str(self.doctor1.pk),
            "procedure_name": "Emergency Bypass",
            "start_time": (start + timedelta(minutes=30)).isoformat(),
            "end_time": (end + timedelta(minutes=30)).isoformat(),
        }
        res_conflict = self.client.post("/api/scheduling/operating-room-schedules/", conflict_payload, format="json")
        self.assertEqual(res_conflict.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Cancel surgical schedule
        res_cancel = self.client.post(f"/api/scheduling/operating-room-schedules/{or_schedule_id}/cancel/")
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cancel.data["status"], "cancelled")

    def test_tenant_scoping_hides_appointments_across_organizations(self):
        # Create an appointment in Org 2
        appt_org2 = Appointment.objects.create(
            patient=self.patient2, doctor=self.doctor1,
            hospital=self.hosp2, department=self.dept2,
            start_time=timezone.now() + timedelta(days=6, hours=10),
            end_time=timezone.now() + timedelta(days=6, hours=10, minutes=30),
            status=Appointment.Status.SCHEDULED, reason="Org 2 Visit",
        )

        # Doctor in Org 1 cannot see or retrieve Appointment in Org 2
        self.client.force_authenticate(user=self.doctor_user)
        res_list = self.client.get("/api/scheduling/appointments/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        # Should not see appt_org2
        ids = [item["id"] for item in res_list.data["results"]]
        self.assertNotIn(str(appt_org2.pk), ids)

        res_detail = self.client.get(f"/api/scheduling/appointments/{appt_org2.pk}/")
        self.assertEqual(res_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_available_slots_api(self):
        # 1. Create schedule with Monday working hours (09:00 - 11:00)
        schedule = DoctorSchedule.objects.create(
            doctor=self.doctor1,
            hospital=self.hosp1,
            department=self.dept1,
            slot_duration_minutes=30,
            buffer_time_minutes=0,
            is_active=True,
        )
        WorkingHours.objects.create(
            doctor_schedule=schedule,
            day_of_week=WorkingHours.DayOfWeek.MONDAY,
            start_time=time(9, 0),
            end_time=time(11, 0),
        )

        today = date.today()
        days_until_next_monday = (0 - today.weekday() + 7) % 7 or 7
        next_monday = today + timedelta(days=days_until_next_monday)

        # Book one slot at 09:30 - 10:00
        start_booked = timezone.make_aware(datetime.combine(next_monday, time(9, 30)))
        end_booked = timezone.make_aware(datetime.combine(next_monday, time(10, 0)))
        Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            hospital=self.hosp1,
            department=self.dept1,
            start_time=start_booked,
            end_time=end_booked,
            status=Appointment.Status.CONFIRMED,
            reason="Follow-up ECG",
        )

        # 2. Call available-slots endpoint
        self.client.force_authenticate(user=self.receptionist)
        res = self.client.get(
            f"/api/scheduling/appointments/available-slots/?doctor={self.doctor1.pk}&date={next_monday.isoformat()}"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        slots = res.data["available_slots"]
        # Expected remaining 3 slots: 09:00 - 09:30, 10:00 - 10:30, 10:30 - 11:00
        self.assertEqual(len(slots), 3)
        start_displays = [s["start_display"] for s in slots]
        self.assertIn("09:00", start_displays)
        self.assertIn("10:00", start_displays)
        self.assertIn("10:30", start_displays)
        self.assertNotIn("09:30", start_displays)

    def test_exceptional_working_day_api_crud(self):
        schedule = DoctorSchedule.objects.create(
            doctor=self.doctor1,
            hospital=self.hosp1,
            department=self.dept1,
            slot_duration_minutes=30,
            is_active=True,
        )

        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "doctor_schedule": str(schedule.pk),
            "date": "2026-12-25",
            "start_time": "10:00:00",
            "end_time": "14:00:00",
            "is_working_day": True,
            "reason": "Holiday on-call coverage",
        }
        res_create = self.client.post("/api/scheduling/exceptional-working-days/", payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        exp_id = res_create.data["id"]

        # List exceptional working days
        res_list = self.client.get(f"/api/scheduling/exceptional-working-days/?doctor_schedule={schedule.pk}")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(res_list.data["count"], 1)

        # Detail retrieve
        res_detail = self.client.get(f"/api/scheduling/exceptional-working-days/{exp_id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data["reason"], "Holiday on-call coverage")

    def test_operating_room_reschedule_and_availability_api(self):
        self.client.force_authenticate(user=self.doctor_user)
        base_date = date.today() + timedelta(days=10)
        s1_start = timezone.make_aware(datetime.combine(base_date, time(8, 0)))
        s1_end = timezone.make_aware(datetime.combine(base_date, time(10, 0)))

        s2_start = timezone.make_aware(datetime.combine(base_date, time(11, 0)))
        s2_end = timezone.make_aware(datetime.combine(base_date, time(13, 0)))

        # 1. Book Surgery 1 and Surgery 2
        res1 = self.client.post("/api/scheduling/operating-room-schedules/", {
            "operating_room": str(self.or1.pk),
            "patient": str(self.patient1.pk),
            "lead_surgeon": str(self.doctor1.pk),
            "procedure_name": "Procedure 1",
            "start_time": s1_start.isoformat(),
            "end_time": s1_end.isoformat(),
            "status": "reserved",
        }, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        s1_id = res1.data["id"]

        res2 = self.client.post("/api/scheduling/operating-room-schedules/", {
            "operating_room": str(self.or1.pk),
            "patient": str(self.patient1.pk),
            "lead_surgeon": str(self.doctor1.pk),
            "procedure_name": "Procedure 2",
            "start_time": s2_start.isoformat(),
            "end_time": s2_end.isoformat(),
            "status": "reserved",
        }, format="json")
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # 2. Reschedule Surgery 1 into conflicting interval with Surgery 2 (11:30 - 12:30)
        res_conflict = self.client.post(
            f"/api/scheduling/operating-room-schedules/{s1_id}/reschedule/",
            {
                "new_start_time": (s2_start + timedelta(minutes=30)).isoformat(),
                "new_end_time": (s2_end - timedelta(minutes=30)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(res_conflict.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Reschedule Surgery 1 to non-conflicting afternoon time (14:00 - 16:00)
        s1_new_start = timezone.make_aware(datetime.combine(base_date, time(14, 0)))
        s1_new_end = timezone.make_aware(datetime.combine(base_date, time(16, 0)))
        res_ok = self.client.post(
            f"/api/scheduling/operating-room-schedules/{s1_id}/reschedule/",
            {
                "new_start_time": s1_new_start.isoformat(),
                "new_end_time": s1_new_end.isoformat(),
            },
            format="json",
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)

        # 4. Check Operating Room availability endpoint for base_date
        res_avail = self.client.get(
            f"/api/scheduling/operating-room-schedules/availability/?operating_room={self.or1.pk}&date={base_date.isoformat()}"
        )
        self.assertEqual(res_avail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_avail.data["total_booked_surgeries"], 2)
        surgeries = res_avail.data["booked_surgeries"]
        self.assertEqual(len(surgeries), 2)


