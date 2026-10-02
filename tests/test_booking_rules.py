import unittest
from datetime import datetime, time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appointment_app import create_app
from appointment_app.extensions import db
from appointment_app.models import Appointment, Availability, CompanyProfile, User
from sqlalchemy.exc import IntegrityError


class BookingRulesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = type(
            "TestConfig",
            (),
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "LOG_FILE": ".test-app.log",
                "LOG_LEVEL": "ERROR",
                "RATELIMIT_STORAGE_URI": "memory://",
                "MAIL_ENABLED": False,
                "PROXY_FIX_X_FOR": 0,
                "PROXY_FIX_X_PROTO": 0,
                "PROXY_FIX_X_HOST": 0,
                "PROXY_FIX_X_PORT": 0,
                "PROXY_FIX_X_PREFIX": 0,
            },
        )
        cls.app = create_app(config)
        cls.context = cls.app.app_context()
        cls.context.push()
        db.create_all()

        owner = User(full_name="Entreprise", email="company@example.test", role="company")
        company = CompanyProfile(user=owner, company_name="Entreprise", public_slug="entreprise")
        db.session.add_all(
            [
                owner,
                company,
                Availability(company=company, weekday=0, start_time=time(9), end_time=time(10)),
            ]
        )
        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        cls.context.pop()

    def setUp(self):
        db.session.query(Appointment).delete()
        db.session.commit()
        self.client = self.app.test_client()

    def _book(self, start_at):
        with self.client.session_transaction() as session:
            session["_csrf_token"] = "test-csrf"
        return self.client.post(
            "/c/entreprise",
            data={
                "csrf_token": "test-csrf",
                "customer_name": "Client",
                "customer_email": "client@example.test",
                "start_at": start_at,
            },
        )

    def test_rejects_non_aligned_slot(self):
        response = self._book("2099-01-05T09:15")  # lundi
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"hors disponibilites", response.data)

    def test_database_prevents_duplicate_active_slot(self):
        self.assertEqual(self._book("2099-01-05T09:00").status_code, 302)
        self.assertEqual(self._book("2099-01-05T09:00").status_code, 200)
        self.assertEqual(Appointment.query.count(), 1)

        duplicate = Appointment(
            company_id=CompanyProfile.query.filter_by(public_slug="entreprise").one().id,
            customer_name="Autre client",
            customer_email="other@example.test",
            start_at=datetime(2099, 1, 5, 9),
            status=Appointment.STATUS_PENDING,
        )
        db.session.add(duplicate)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
