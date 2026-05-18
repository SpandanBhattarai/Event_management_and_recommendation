import io
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from accounts.models import UserProfile
from .email_utils import build_ticket_context, render_ticket_pdf_html
from .models import Category, Event, TicketPurchase, Venue
from .views import _get_popularity_display_percent


class PopularityDisplayTests(TestCase):
    def test_popularity_display_percent_is_boosted_and_capped(self):
        self.assertEqual(_get_popularity_display_percent(0.4), 50)
        self.assertEqual(_get_popularity_display_percent(1), 99)  


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
        self.assertIn("Hello sabin, please find your ticket details below:", email.body)
        self.assertIn("Thank you,\nEventMandu team", email.body)
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

    def test_completed_purchases_remain_separate_transactions(self):
        older_purchase = TicketPurchase.objects.create(
            user=self.user,
            event=self.event,
            quantity=5,
            total_amount="7500.00",
            status=TicketPurchase.STATUS_COMPLETED,
            khalti_txn_id="txn-old",
            purchase_order_id="order-old",
        )
        new_purchase = TicketPurchase.objects.create(
            user=self.user,
            event=self.event,
            quantity=2,
            total_amount="3000.00",
            status=TicketPurchase.STATUS_INITIATED,
            khalti_pidx="pidx-merge",
            purchase_order_id="order-new",
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("khalti_return"),
            {"status": "Completed", "pidx": "pidx-merge", "transaction_id": "txn-new"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(TicketPurchase.objects.filter(id=new_purchase.id).exists())
        new_purchase.refresh_from_db()
        self.assertEqual(new_purchase.status, TicketPurchase.STATUS_COMPLETED)
        self.assertEqual(new_purchase.quantity, 2)
        self.assertEqual(new_purchase.total_amount, Decimal("3000.00"))
        older_purchase.refresh_from_db()
        self.assertEqual(older_purchase.quantity, 5)
        self.assertEqual(older_purchase.total_amount, Decimal("7500.00"))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Quantity: 2", email.body)
        self.assertIn("Total Paid: NPR 3000.00", email.body)
        self.assertIn("Order ID: order-new", email.body)

    @override_settings(KHALTI_SECRET_KEY="test-secret")
    @patch("events.views.urllib_request.urlopen")
    def test_reinitiating_active_khalti_hold_replaces_quantity(self, mock_urlopen):
        class FakeKhaltiResponse:
            def __init__(self, pidx):
                self.pidx = pidx

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "payment_url": f"https://khalti.test/pay/{self.pidx}",
                        "pidx": self.pidx,
                    }
                ).encode("utf-8")

        mock_urlopen.side_effect = [
            FakeKhaltiResponse("pidx-first"),
            FakeKhaltiResponse("pidx-second"),
        ]

        self.client.force_login(self.user)

        first_response = self.client.post(
            reverse("buy_ticket", args=[self.event.id]),
            {"ticket_quantity": "1", "payment_method": "khalti"},
        )
        second_response = self.client.post(
            reverse("buy_ticket", args=[self.event.id]),
            {"ticket_quantity": "1", "payment_method": "khalti"},
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(TicketPurchase.objects.filter(user=self.user, event=self.event).count(), 1)

        purchase = TicketPurchase.objects.get(user=self.user, event=self.event)
        self.assertEqual(purchase.quantity, 1)
        self.assertEqual(purchase.total_amount, Decimal("1500.00"))
        self.assertEqual(purchase.khalti_pidx, "pidx-second")

        sent_amounts = [
            json.loads(call.args[0].data.decode("utf-8"))["amount"]
            for call in mock_urlopen.call_args_list
        ]
        self.assertEqual(sent_amounts, [150000, 150000])

    def test_ticket_owner_can_download_pdf_from_tickets_page_route(self):
        purchase = TicketPurchase.objects.create(
            user=self.user,
            event=self.event,
            quantity=1,
            total_amount="1500.00",
            status=TicketPurchase.STATUS_COMPLETED,
            khalti_txn_id="txn-download",
            purchase_order_id="order-download",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("ticket_pdf_download", args=[purchase.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("eventmandu-ticket-order-download.pdf", response["Content-Disposition"])

    def test_ticket_download_is_blocked_for_ended_events(self):
        ended_event = Event.objects.create(
            title="Past Show",
            description="Past event",
            venue=self.venue,
            category=self.category,
            start_date=timezone.now() - timedelta(days=3),
            end_date=timezone.now() - timedelta(days=2),
            price="1200.00",
            approval_status=Event.APPROVAL_APPROVED,
            is_finished=True,
        )
        purchase = TicketPurchase.objects.create(
            user=self.user,
            event=ended_event,
            quantity=1,
            total_amount="1200.00",
            status=TicketPurchase.STATUS_COMPLETED,
            khalti_txn_id="txn-ended",
            purchase_order_id="order-ended",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("ticket_pdf_download", args=[purchase.id]))

        self.assertEqual(response.status_code, 403)

    def test_ticket_context_prefers_profile_fields_for_holder_phone_and_timezone(self):
        profile = self.user.profile
        profile.ticket_holder_name = "Sabin Shrestha"
        profile.phone_number = "+977-9812345678"
        profile.timezone = "Asia/Kathmandu"
        profile.save()
        purchase = TicketPurchase.objects.create(
            user=self.user,
            event=self.event,
            quantity=1,
            total_amount="1500.00",
            status=TicketPurchase.STATUS_COMPLETED,
            khalti_txn_id="txn-profile",
            purchase_order_id="order-profile",
        )

        context = build_ticket_context(purchase)

        self.assertEqual(context["attendee_name"], "Sabin Shrestha")
        self.assertEqual(context["attendee_phone"], "+977-9812345678")
        self.assertEqual(profile.timezone, "Asia/Kathmandu")
