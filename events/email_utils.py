from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas


def _ticket_salutation(purchase_time):
    local_time = timezone.localtime(purchase_time)
    hour = local_time.hour
    if 5 <= hour < 12:
        return "Good morning!"
    if 12 <= hour < 17:
        return "Good afternoon!"
    if 17 <= hour < 21:
        return "Good evening!"
    return "Hello!"


def _ticket_details_lines(purchase):
    event = purchase.event
    venue = event.venue
    local_purchase_time = timezone.localtime(purchase.created_at)
    local_start = timezone.localtime(event.start_date)
    local_end = timezone.localtime(event.end_date)
    return [
        f"Event: {event.title}",
        f"Venue: {venue.name}",
        f"Location: {venue.city} - {venue.address}",
        f"Starts: {local_start.strftime('%b %d, %Y %I:%M %p')}",
        f"Ends: {local_end.strftime('%b %d, %Y %I:%M %p')}",
        f"Quantity: {purchase.quantity}",
        f"Total Paid: NPR {purchase.total_amount}",
        f"Order ID: {purchase.purchase_order_id}",
        f"Transaction ID: {purchase.khalti_txn_id or 'Pending confirmation'}",
        f"Purchased At: {local_purchase_time.strftime('%b %d, %Y %I:%M %p')}",
    ]


def _ticket_holder_name(user):
    full_name = f"{user.first_name} {user.last_name}".strip()
    return full_name or user.username


def _ticket_status_meta(status):
    mapping = {
        "completed": ("Confirmed", "#16a34a"),
        "initiated": ("Pending", "#f59e0b"),
        "canceled": ("Cancelled", "#dc2626"),
        "failed": ("Cancelled", "#dc2626"),
    }
    return mapping.get(status, ("Pending", "#f59e0b"))


def build_ticket_context(purchase):
    event = purchase.event
    venue = event.venue
    user = purchase.user
    local_purchase_time = timezone.localtime(purchase.created_at)
    local_start = timezone.localtime(event.start_date)
    local_end = timezone.localtime(event.end_date)
    status_label, status_color = _ticket_status_meta(purchase.status)
    total_amount = Decimal(purchase.total_amount)
    unit_price = total_amount / max(purchase.quantity, 1)

    return {
        "brand_name": "EventMandu",
        "booking_id": purchase.purchase_order_id,
        "booking_date": local_purchase_time,
        "status_label": status_label,
        "status_color": status_color,
        "event_name": event.title,
        "event_type": event.category.name if event.category else "General Event",
        "venue_name": venue.name,
        "venue_address": venue.address,
        "venue_city": venue.city,
        "event_start": local_start,
        "event_end": local_end,
        "attendee_name": _ticket_holder_name(user),
        "attendee_phone": getattr(user, "phone_number", "") or "Not provided",
        "attendee_email": user.email or "Not provided",
        "ticket_rows": [
            {
                "ticket_type": "Standard Entry",
                "quantity": purchase.quantity,
                "price": unit_price,
                "total": total_amount,
            }
        ],
        "subtotal": total_amount,
        "total_amount": total_amount,
        "transaction_id": purchase.khalti_txn_id or "Pending confirmation",
        "support_email": "support@eventmandu.com",
        "support_phone": "+977-9800000000",
        "logo_text": "EM",
    }


def render_ticket_pdf_html(purchase):
    return render_to_string("pdf/event_ticket.html", build_ticket_context(purchase))


def _build_ticket_email_body(purchase):
    lines = [
        _ticket_salutation(purchase.created_at),
        "",
        f"hello {purchase.user.username}, please find your ticket details below:",
        "",
        *_ticket_details_lines(purchase),
        "",
        "thank you,",
        "eventmandu team",
    ]
    return "\n".join(lines)


def _draw_wrapped_text(pdf, text, x, y, width, font_name="Helvetica", font_size=11, color=colors.black, leading=14):
    pdf.setFillColor(color)
    pdf.setFont(font_name, font_size)
    lines = simpleSplit(str(text), font_name, font_size, width)
    for line in lines:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _draw_label_value(pdf, label, value, x, y, width):
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x, y, label.upper())
    return _draw_wrapped_text(
        pdf,
        value,
        x,
        y - 14,
        width,
        font_name="Helvetica-Bold",
        font_size=12,
        color=colors.HexColor("#183153"),
        leading=15,
    )


def _format_money(amount):
    return f"NPR {Decimal(amount):,.2f}"


def _build_reportlab_ticket_pdf(purchase):
    context = build_ticket_context(purchase)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    page_width, page_height = A4

    outer_margin = 32
    card_x = outer_margin
    card_y = 58
    card_width = page_width - (outer_margin * 2)
    card_height = page_height - 116
    top_y = card_y + card_height

    pdf.setTitle(f"{context['brand_name']} Ticket")

    pdf.setFillColor(colors.HexColor("#f4f8fd"))
    pdf.rect(0, 0, page_width, page_height, stroke=0, fill=1)

    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor("#d8e3f2"))
    pdf.roundRect(card_x, card_y, card_width, card_height, 18, stroke=1, fill=1)

    header_height = 136
    header_y = top_y - header_height
    pdf.setFillColor(colors.HexColor("#1f6bff"))
    pdf.roundRect(card_x, header_y, card_width, header_height, 18, stroke=0, fill=1)
    pdf.rect(card_x, header_y, card_width, header_height - 18, stroke=0, fill=1)

    badge_size = 42
    badge_x = card_x + 24
    badge_y = top_y - 60
    pdf.setFillColor(colors.white)
    pdf.roundRect(badge_x, badge_y, badge_size, badge_size, 12, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#1f6bff"))
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(badge_x + (badge_size / 2), badge_y + 14, context["logo_text"])

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(card_x + 24, top_y - 84, context["brand_name"])
    pdf.setFont("Helvetica", 11)
    pdf.setFillColor(colors.HexColor("#dce8ff"))
    pdf.drawString(card_x + 24, top_y - 98, "Premium event ticket and booking invoice")

    right_x = card_x + card_width - 220
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(right_x, top_y - 42, "BOOKING ID")
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawRightString(card_x + card_width - 24, top_y - 58, context["booking_id"])

    badge_w = 82
    badge_h = 24
    badge_right = card_x + card_width - 24
    badge_left = badge_right - badge_w
    badge_y = top_y - 92
    pdf.setFillColor(colors.white)
    pdf.roundRect(badge_left, badge_y, badge_w, badge_h, 12, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor(context["status_color"]))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(badge_left + (badge_w / 2), badge_y + 8, context["status_label"])

    pdf.setFillColor(colors.HexColor("#e7efff"))
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(card_x + card_width - 24, top_y - 108, f"Booked on {context['booking_date'].strftime('%b %d, %Y at %I:%M %p')}")

    content_left = card_x + 24
    content_width = card_width - 48
    footer_base_y = card_y + 22
    footer_top_y = footer_base_y + 44
    y = header_y - 20

    pdf.setFillColor(colors.HexColor("#3275ff"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(content_left, y, "YOUR EVENT PASS")
    y -= 26

    pdf.setFillColor(colors.HexColor("#162d50"))
    pdf.setFont("Helvetica-Bold", 23)
    event_lines = simpleSplit(context["event_name"], "Helvetica-Bold", 23, content_width)
    for line in event_lines[:2]:
        pdf.drawString(content_left, y, line)
        y -= 26

    pdf.setFillColor(colors.HexColor("#e9f1ff"))
    pdf.roundRect(content_left, y - 2, 86, 20, 10, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#205bd8"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(content_left + 10, y + 5, context["event_type"])
    y -= 24

    pdf.setStrokeColor(colors.HexColor("#cfdbeb"))
    pdf.line(content_left, y, card_x + card_width - 24, y)
    y -= 18

    pdf.setFillColor(colors.HexColor("#163258"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(content_left, y, "Event Details")
    y -= 16

    y = _draw_label_value(
        pdf,
        "Location",
        f"{context['venue_name']}, {context['venue_city']}, {context['venue_address']}",
        content_left,
        y,
        content_width,
    ) - 8
    y = _draw_label_value(
        pdf,
        "Starts",
        context["event_start"].strftime("%b %d, %Y at %I:%M %p"),
        content_left,
        y,
        content_width,
    ) - 8
    y = _draw_label_value(
        pdf,
        "Ends",
        context["event_end"].strftime("%b %d, %Y at %I:%M %p"),
        content_left,
        y,
        content_width,
    ) - 8

    pdf.line(content_left, y, card_x + card_width - 24, y)
    y -= 18

    pdf.setFillColor(colors.HexColor("#163258"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(content_left, y, "User Details")
    y -= 16

    y = _draw_label_value(pdf, "Name", context["attendee_name"], content_left, y, content_width) - 8
    y = _draw_label_value(pdf, "Phone Number", context["attendee_phone"], content_left, y, content_width) - 8
    y = _draw_label_value(pdf, "Email", context["attendee_email"], content_left, y, content_width) - 8

    pdf.line(content_left, y, card_x + card_width - 24, y)
    y -= 18

    pdf.setFillColor(colors.HexColor("#163258"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(content_left, y, "Ticket Details")
    y -= 16

    table_x = content_left
    table_width = content_width
    col_widths = [table_width * 0.40, table_width * 0.16, table_width * 0.20, table_width * 0.24]
    row_height = 24

    pdf.setFillColor(colors.HexColor("#edf4ff"))
    pdf.roundRect(table_x, y - row_height + 6, table_width, row_height, 8, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#28466f"))
    pdf.setFont("Helvetica-Bold", 10)
    headers = ["Ticket Type", "Quantity", "Price", "Total"]
    cursor_x = table_x + 10
    for header, width in zip(headers, col_widths):
        pdf.drawString(cursor_x, y - 10, header)
        cursor_x += width

    y -= 30
    row = context["ticket_rows"][0]
    values = [
        row["ticket_type"],
        str(row["quantity"]),
        _format_money(row["price"]),
        _format_money(row["total"]),
    ]
    cursor_x = table_x + 10
    pdf.setFillColor(colors.HexColor("#183153"))
    pdf.setFont("Helvetica", 10)
    for index, (value, width) in enumerate(zip(values, col_widths)):
        if index >= 2:
            pdf.drawRightString(cursor_x + width - 10, y - 2, value)
        else:
            pdf.drawString(cursor_x, y - 2, value)
        cursor_x += width
    y -= 18

    if y < footer_top_y + 86:
        y = footer_top_y + 86

    pdf.line(content_left, y, card_x + card_width - 24, y)
    y -= 18

    pdf.setFillColor(colors.HexColor("#163258"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(content_left, y, "Payment Summary")

    right_value_x = card_x + card_width - 24
    y -= 16
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.drawString(content_left, y, "SUBTOTAL")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(colors.HexColor("#183153"))
    pdf.drawRightString(right_value_x, y, _format_money(context["subtotal"]))

    y -= 20
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.drawString(content_left, y, "TOTAL AMOUNT")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.setFillColor(colors.HexColor("#1657df"))
    pdf.drawRightString(right_value_x, y, _format_money(context["total_amount"]))

    y -= 18
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.drawString(content_left, y, "STATUS")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors.HexColor(context["status_color"]))
    pdf.drawString(content_left + 58, y, context["status_label"])
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(content_left + 150, y, "TXN ID")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.HexColor("#183153"))
    pdf.drawString(content_left + 190, y, str(context["transaction_id"]))

    pdf.setStrokeColor(colors.HexColor("#dce6f3"))
    pdf.line(content_left, footer_top_y, card_x + card_width - 24, footer_top_y)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(colors.HexColor("#5f738f"))
    pdf.drawString(content_left, footer_base_y + 24, "This is a digitally generated ticket.")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(content_left, footer_base_y + 12, f"Support: {context['support_email']} | {context['support_phone']}")
    pdf.drawString(content_left, footer_base_y, "Terms: non-refundable. Please show this ticket or QR at entry if requested by the organizer.")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_ticket_pdf(purchase):
    return _build_reportlab_ticket_pdf(purchase)


def send_ticket_email(purchase):
    recipient = purchase.user.email
    if not recipient:
        return False

    email = EmailMessage(
        subject="event tickets from eventmandu",
        body=_build_ticket_email_body(purchase),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    email.attach(
        f"eventmandu-ticket-{purchase.purchase_order_id}.pdf",
        build_ticket_pdf(purchase),
        "application/pdf",
    )
    email.send(fail_silently=False)
    return True
