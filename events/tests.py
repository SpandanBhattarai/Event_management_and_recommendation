import io
from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from .email_utils import render_ticket_pdf_html
from .models import Category, Event, TicketPurchase, Venue


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="eventmandu5@gmail.com",
    TIME_ZONE="UTC",
)
class TicketEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sabin",
            email="sabin@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(name="Concert")
        self.venue = Venue.objects.create(
            name="Town Hall",
            address="Durbar Marg",
            capacity=500,
            latitude=27.7172,
            longitude=85.3240,
            city="Kathmandu",
        )
        self.event = Event.objects.create(
            title="Spring Music Night",
            description="Live music event",
            venue=self.venue,
            category=self.category,
            start_date=timezone.now() + timedelta(days=2),
            end_date=timezone.now() + timedelta(days=2, hours=3),
            price="1500.00",
            approval_status=Event.APPROVAL_APPROVED,
        )

    def test_completed_payment_sends_ticket_email_with_pdf_attachment(self):
        purchase = TicketPurchase.objects.create(
            user=self.user,
            event=self.event,
            quantity=2,
            total_amount="3000.00",
            status=TicketPurchase.STATUS_INITIATED,
            khalti_pidx="pidx-123",
            purchase_order_id="order-123",
        )
        TicketPurchase.objects.filter(id=purchase.id).update(
            created_at=datetime(2026, 4, 6, 9, 15, tzinfo=dt_timezone.utc)
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("khalti_return"),
            {"status": "Completed", "pidx": "pidx-123", "transaction_id": "txn-123"},
        )

        self.assertEqual(response.status_code, 302)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, TicketPurchase.STATUS_COMPLETED)
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox[0]
        self.assertEqual(email.subject, "event tickets from eventmandu")
        self.assertIn("Good morning!", email.body)
        self.assertIn("hello sabin, please find your ticket details below:", email.body)
        self.assertIn("thank you,\neventmandu team", email.body)
        self.assertEqual(len(email.attachments), 1)

        attachment = email.attachments[0]
        self.assertEqual(attachment[0], "eventmandu-ticket-order-123.pdf")
        self.assertEqual(attachment[2], "application/pdf")
        self.assertTrue(attachment[1].startswith(b"%PDF-1.4"))
        reader = PdfReader(io.BytesIO(attachment[1]))
        self.assertEqual(len(reader.pages), 1)
        self.assertIn("EventMandu", reader.pages[0].extract_text())

    def test_ticket_pdf_html_template_contains_premium_sections(self):
        purchase = TicketPurchase.objects.create(
            user=self.user,
            event=self.event,
            quantity=2,
            total_amount="3000.00",
            status=TicketPurchase.STATUS_COMPLETED,
            khalti_txn_id="txn-123",
            purchase_order_id="order-456",
        )

        html = render_ticket_pdf_html(purchase)

        self.assertIn("EventMandu", html)
        self.assertIn("Booking ID", html)
        self.assertIn("User Details", html)
        self.assertIn("Ticket Details", html)
        self.assertIn("Payment Summary", html)
        self.assertIn("Standard Entry", html)
        self.assertIn("This is a digitally generated ticket.", html)
