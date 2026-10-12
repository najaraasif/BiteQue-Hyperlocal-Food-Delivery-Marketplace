import io

from PIL import Image as PILImage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from rider_app.tests.test_assignment_flow import make_rider, make_user

from .forms import (
    BankDetailsForm,
    DeliveryOTPForm,
    RiderAdminForm,
    RiderLoginForm,
    RiderPasswordResetForm,
    RiderRegistrationForm,
)
from .models import Rider, RiderBankAccount


def png_upload(name):
    buffer = io.BytesIO()
    PILImage.new('RGB', (8, 8), (40, 90, 200)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def valid_payload(**overrides):
    data = {
        'username': 'rider_form_user',
        'email': 'rider_form@example.com',
        'password1': 'Str0ngPassphrase!',
        'password2': 'Str0ngPassphrase!',
        'full_name': 'Form Rider',
        'phone': '9876543210',
        'gender': 'M',
        'aadhar_number': '123456789012',
        'driving_license': 'DLFORM123456',
        'address': '1 Test Lane',
        'area': 'Test Area',
        'pincode': '123456',
    }
    data.update(overrides)
    return data


def valid_files(**overrides):
    files = {
        'profile_photo': png_upload('profile.png'),
        'aadhar_front': png_upload('front.png'),
        'aadhar_back': png_upload('back.png'),
        'license_copy': png_upload('license.png'),
    }
    files.update(overrides)
    return files


class RiderRegistrationFormValidTests(TestCase):
    def test_complete_payload_is_valid(self):
        form = RiderRegistrationForm(valid_payload(), valid_files())
        self.assertTrue(form.is_valid(), form.errors)
        cleaned = form.cleaned_data
        self.assertEqual(cleaned['full_name'], 'Form Rider')
        self.assertEqual(cleaned['phone'], '9876543210')
        self.assertEqual(cleaned['aadhar_number'], '123456789012')
        self.assertEqual(cleaned['driving_license'], 'DLFORM123456')
        self.assertEqual(cleaned['pincode'], '123456')
        self.assertEqual(cleaned['gender'], 'M')

    def test_save_creates_user_with_hashed_password(self):
        form = RiderRegistrationForm(valid_payload(), valid_files())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        user.refresh_from_db()
        self.assertEqual(user.username, 'rider_form_user')
        self.assertEqual(user.email, 'rider_form@example.com')
        self.assertTrue(user.check_password('Str0ngPassphrase!'))
        self.assertNotEqual(user.password, 'Str0ngPassphrase!')

    def test_multi_word_full_name_stays_in_cleaned_data(self):
        form = RiderRegistrationForm(
            valid_payload(full_name='Mary Jane Watson'), valid_files()
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['full_name'], 'Mary Jane Watson'
        )


class RiderRegistrationFieldTests(TestCase):
    def assert_invalid(self, data, files, field, message=None):
        form = RiderRegistrationForm(data, files)
        self.assertFalse(form.is_valid())
        self.assertIn(field, form.errors)
        if message:
            self.assertIn(message, form.errors[field][0])

    def test_required_text_fields(self):
        for field in (
            'full_name', 'phone', 'gender', 'address', 'area', 'pincode',
            'aadhar_number', 'driving_license',
        ):
            with self.subTest(field=field):
                data = valid_payload()
                data.pop(field)
                self.assert_invalid(data, valid_files(), field)

    def test_required_image_fields(self):
        for field in (
            'profile_photo', 'aadhar_front', 'aadhar_back', 'license_copy',
        ):
            with self.subTest(field=field):
                files = valid_files()
                files.pop(field)
                self.assert_invalid(valid_payload(), files, field)

    def test_username_is_required_by_user_creation_form(self):
        data = valid_payload()
        data.pop('username')
        self.assert_invalid(data, valid_files(), 'username')

    def test_short_phone_is_rejected(self):
        self.assert_invalid(
            valid_payload(phone='12345'), valid_files(), 'phone',
            'at least 10 digits',
        )

    def test_non_digit_phone_is_rejected(self):
        self.assert_invalid(
            valid_payload(phone='call-me-now'), valid_files(), 'phone',
            'at least 10 digits',
        )

    def test_eleven_digit_phone_is_accepted(self):
        form = RiderRegistrationForm(
            valid_payload(phone='919876543210'), valid_files()
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_short_aadhar_is_rejected(self):
        self.assert_invalid(
            valid_payload(aadhar_number='12345678901'), valid_files(),
            'aadhar_number', 'exactly 12 digits',
        )

    def test_non_digit_aadhar_is_rejected(self):
        self.assert_invalid(
            valid_payload(aadhar_number='abcdefghijkl'), valid_files(),
            'aadhar_number', 'exactly 12 digits',
        )

    def test_duplicate_aadhar_is_rejected(self):
        user = make_user('aadhar_holder')
        Rider.objects.create(
            user=user, phone='9876543210', gender='M',
            aadhar_number='123456789012', driving_license='DLUNIQUE001',
            address='1 Road', area='Area', pincode='123456',
            profile_photo='riders/profiles/a.jpg',
            aadhar_front='riders/aadhar/a.jpg',
            license_copy='riders/license/a.jpg',
        )
        self.assert_invalid(
            valid_payload(), valid_files(), 'aadhar_number',
            'already registered',
        )

    def test_short_license_is_rejected(self):
        self.assert_invalid(
            valid_payload(driving_license='SHORT1'), valid_files(),
            'driving_license', 'at least 10 characters',
        )

    def test_duplicate_license_is_rejected(self):
        user = make_user('license_holder')
        Rider.objects.create(
            user=user, phone='9876543210', gender='M',
            aadhar_number='223456789012', driving_license='DLFORM123456',
            address='1 Road', area='Area', pincode='123456',
            profile_photo='riders/profiles/b.jpg',
            aadhar_front='riders/aadhar/b.jpg',
            license_copy='riders/license/b.jpg',
        )
        self.assert_invalid(
            valid_payload(), valid_files(), 'driving_license',
            'already registered',
        )

    def test_non_digit_pincode_is_rejected(self):
        self.assert_invalid(
            valid_payload(pincode='12AB56'), valid_files(), 'pincode',
            'exactly 6 digits',
        )

    def test_short_pincode_is_rejected(self):
        self.assert_invalid(
            valid_payload(pincode='12345'), valid_files(), 'pincode',
            'exactly 6 digits',
        )

    def test_password_mismatch_is_rejected(self):
        self.assert_invalid(
            valid_payload(password2='DifferentPass!'), valid_files(),
            'password2',
        )

    def test_too_short_password_is_rejected(self):
        self.assert_invalid(
            valid_payload(password1='Sh0rt!', password2='Sh0rt!'),
            valid_files(), 'password2',
        )

    def test_unlisted_gender_is_rejected(self):
        self.assert_invalid(
            valid_payload(gender='X'), valid_files(), 'gender',
        )


class RiderLoginFormTests(TestCase):
    def make_form(self, username, password):
        return RiderLoginForm(
            data={'username': username, 'password': password}
        )

    def test_approved_rider_can_log_in(self):
        rider = make_rider('login_ok_rider')
        form = self.make_form(rider.user.username, 'pw12345678')
        self.assertTrue(form.is_valid(), form.errors)

    def test_user_without_rider_profile_is_rejected(self):
        plain = make_user('plain_login_user')
        form = self.make_form(plain.username, 'pw12345678')
        self.assertFalse(form.is_valid())
        self.assertIn(
            "This account doesn't have a rider profile.",
            form.errors['__all__'],
        )

    def test_unapproved_rider_is_rejected(self):
        rider = make_rider('pending_login_rider', approved=False)
        form = self.make_form(rider.user.username, 'pw12345678')
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Your rider account is pending approval.',
            form.errors['__all__'],
        )

    def test_wrong_password_is_rejected_without_rider_message(self):
        rider = make_rider('wrong_pw_rider')
        form = self.make_form(rider.user.username, 'not-the-password')
        self.assertFalse(form.is_valid())
        messages = form.errors.get('__all__', [])
        self.assertTrue(messages)
        self.assertFalse(any('rider profile' in m for m in messages))

    def test_username_widget_styling(self):
        form = RiderLoginForm()
        widget = form.fields['username'].widget
        self.assertEqual(
            widget.attrs['class'], 'w-full px-4 py-2 border rounded-lg'
        )
        self.assertEqual(widget.attrs['placeholder'], 'Username')

    def test_password_widget_styling(self):
        form = RiderLoginForm()
        widget = form.fields['password'].widget
        self.assertEqual(
            widget.attrs['class'], 'w-full px-4 py-2 border rounded-lg'
        )
        self.assertEqual(widget.attrs['placeholder'], 'Password')


class RiderPasswordResetFormTests(TestCase):
    def test_rider_email_is_accepted(self):
        rider = make_rider('reset_rider')
        rider.user.email = 'reset_rider@example.com'
        rider.user.save()
        form = RiderPasswordResetForm(
            data={'email': 'reset_rider@example.com'}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_customer_email_is_rejected(self):
        customer = make_user('reset_customer')
        customer.email = 'reset_customer@example.com'
        customer.save()
        form = RiderPasswordResetForm(
            data={'email': 'reset_customer@example.com'}
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'This email is not registered as a rider.',
            form.errors['email'],
        )

    def test_unknown_email_is_rejected(self):
        form = RiderPasswordResetForm(data={'email': 'ghost@example.com'})
        self.assertFalse(form.is_valid())
        self.assertIn(
            'This email is not registered as a rider.',
            form.errors['email'],
        )

    def test_malformed_email_is_rejected(self):
        form = RiderPasswordResetForm(data={'email': 'not-an-email'})
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_email_widget_styling(self):
        form = RiderPasswordResetForm()
        widget = form.fields['email'].widget
        self.assertEqual(
            widget.attrs['placeholder'], 'Enter your email address'
        )


class BankDetailsFormTests(TestCase):
    def setUp(self):
        self.rider = make_rider('bank_form_rider')

    def base_data(self, **overrides):
        data = {
            'account_holder_name': 'Bank Rider',
            'account_number': '12345678901',
            'bank_name': 'Test Bank',
            'ifsc_code': 'SBIN0000123',
        }
        data.update(overrides)
        return data

    def save_form(self, form):
        account = form.save(commit=False)
        account.rider = self.rider
        account.save()
        return account

    def test_valid_account_is_accepted(self):
        form = BankDetailsForm(
            self.base_data(), rider=self.rider
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_non_digit_account_number_is_rejected(self):
        form = BankDetailsForm(
            self.base_data(account_number='12345abc890'),
            rider=self.rider,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Account number should contain only digits',
            form.errors['account_number'],
        )

    def test_short_account_number_is_rejected(self):
        form = BankDetailsForm(
            self.base_data(account_number='1234567890'),
            rider=self.rider,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Account number too short', form.errors['account_number']
        )

    def test_ifsc_must_be_eleven_characters(self):
        form = BankDetailsForm(
            self.base_data(ifsc_code='SBIN000012'), rider=self.rider
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'IFSC code must be 11 characters long',
            form.errors['ifsc_code'],
        )

    def test_missing_required_fields(self):
        form = BankDetailsForm({}, rider=self.rider)
        self.assertFalse(form.is_valid())
        for field in (
            'account_holder_name', 'account_number', 'bank_name',
            'ifsc_code',
        ):
            with self.subTest(field=field):
                self.assertIn(field, form.errors)

    def test_first_account_becomes_primary_by_default(self):
        form = BankDetailsForm(
            self.base_data(), rider=self.rider
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data['is_primary'])
        saved = self.save_form(form)
        self.assertTrue(saved.is_primary)

    def test_second_account_stays_non_primary(self):
        first = BankDetailsForm(
            self.base_data(), rider=self.rider
        )
        self.assertTrue(first.is_valid(), first.errors)
        self.save_form(first)

        second = BankDetailsForm(
            self.base_data(account_number='22345678901'),
            rider=self.rider,
        )
        self.assertTrue(second.is_valid(), second.errors)
        self.assertFalse(second.cleaned_data['is_primary'])
        saved = self.save_form(second)
        self.assertFalse(saved.is_primary)
        self.assertEqual(
            RiderBankAccount.objects.filter(
                rider=self.rider, is_primary=True
            ).count(),
            1,
        )

    def test_account_number_widget_placeholder(self):
        form = BankDetailsForm()
        widget = form.fields['account_number'].widget
        self.assertEqual(
            widget.attrs['placeholder'], 'Enter 11-18 digit account number'
        )


class DeliveryOTPFormTests(TestCase):
    def form(self, otp):
        return DeliveryOTPForm(data={'otp': otp})

    def test_four_digit_pin_is_valid(self):
        form = self.form('1234')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['otp'], '1234')

    def test_six_digit_pin_is_valid(self):
        form = self.form('123456')
        self.assertTrue(form.is_valid(), form.errors)

    def test_three_digit_pin_is_rejected(self):
        form = self.form('123')
        self.assertFalse(form.is_valid())
        self.assertIn('otp', form.errors)

    def test_five_digit_pin_is_rejected(self):
        form = self.form('12345')
        self.assertFalse(form.is_valid())
        self.assertIn('otp', form.errors)

    def test_letters_are_rejected(self):
        form = self.form('12ab')
        self.assertFalse(form.is_valid())
        self.assertIn(
            'PIN must only contain digits.', form.errors['otp']
        )

    def test_empty_pin_is_rejected(self):
        form = self.form('')
        self.assertFalse(form.is_valid())
        self.assertIn('otp', form.errors)

    def test_widget_declares_numeric_input(self):
        widget = DeliveryOTPForm().fields['otp'].widget
        self.assertEqual(widget.attrs['inputmode'], 'numeric')
        self.assertEqual(widget.attrs['pattern'], '\\d*')
        self.assertEqual(widget.attrs['placeholder'], 'Enter 4 digit PIN')
        self.assertEqual(widget.attrs['maxlength'], '6')
        self.assertEqual(widget.attrs['minlength'], '4')


class RiderAdminFormTests(TestCase):
    def test_username_and_email_fields_absent_from_rider_form(self):
        form = RiderAdminForm()
        self.assertNotIn('username', form.fields)
        self.assertNotIn('email', form.fields)

    def test_form_exposes_approval_and_location_fields(self):
        form = RiderAdminForm()
        for field in (
            'user', 'phone', 'gender', 'is_approved', 'is_available',
            'address', 'area', 'pincode',
        ):
            with self.subTest(field=field):
                self.assertIn(field, form.fields)

    def test_form_covers_the_editable_rider_model_fields(self):
        form = RiderAdminForm()
        model_fields = {
            f.name for f in Rider._meta.concrete_fields
            if f.editable and f.name != 'id'
        }
        self.assertTrue(model_fields.issubset(set(form.fields)))
