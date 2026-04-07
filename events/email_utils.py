from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas


def _ticket_salutation(purchase_time):
    local_time = timezone.localtime(purchase_time, ZoneInfo(settings.TIME_ZONE))
    hour = local_time.hour
    if 5 <= hour < 12:
        return "Good morning! Greetings from EventMandu."
    if 12 <= hour < 17:
        return "Good afternoon! Greetings from EventMandu."
    if 17 <= hour < 21:
        return "Good evening! Greetings from EventMandu."
    return "Greetings from EventMandu."


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


def build_purchase_snapshot(purchase):
    return {
        "quantity": int(purchase.quantity),
        "total_amount": Decimal(purchase.total_amount),
        "purchase_order_id": purchase.purchase_order_id,
        "transaction_id": purchase.khalti_txn_id or "Pending confirmation",
        "created_at": purchase.created_at,
        "status": purchase.status,
    }


def build_ticket_context(purchase, purchase_snapshot=None):
    event = purchase.event
    venue = event.venue
    user = purchase.user
    snapshot = purchase_snapshot or build_purchase_snapshot(purchase)
    local_purchase_time = timezone.localtime(snapshot["created_at"])
    local_start = timezone.localtime(event.start_date)
    local_end = timezone.localtime(event.end_date)
    status_label, status_color = _ticket_status_meta(snapshot["status"])
    total_amount = Decimal(snapshot["total_amount"])
    quantity = int(snapshot["quantity"])
    unit_price = total_amount / max(quantity, 1)

    return {
        "brand_name": "EventMandu",
        "booking_id": snapshot["purchase_order_id"],
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
                "quantity": quantity,
                "price": unit_price,
                "total": total_amount,
            }
        ],
        "subtotal": total_amount,
        "total_amount": total_amount,
        "transaction_id": snapshot["transaction_id"],
        "support_email": "support@eventmandu.com",
        "support_phone": "+977-9800000000",
    }


def render_ticket_pdf_html(purchase, purchase_snapshot=None):
    return render_to_string("pdf/event_ticket.html", build_ticket_context(purchase, purchase_snapshot=purchase_snapshot))


def _build_ticket_email_body(purchase, purchase_snapshot=None):
    snapshot = purchase_snapshot or build_purchase_snapshot(purchase)
    local_purchase_time = timezone.localtime(snapshot["created_at"])
    local_start = timezone.localtime(purchase.event.start_date)
    local_end = timezone.localtime(purchase.event.end_date)
    lines = [
        _ticket_salutation(snapshot["created_at"]),
        "",
        f"Hello {purchase.user.username}, please find your ticket details below:",
        "",
        f"Event: {purchase.event.title}",
        f"Venue: {purchase.event.venue.name}",
        f"Location: {purchase.event.venue.city} - {purchase.event.venue.address}",
        f"Starts: {local_start.strftime('%b %d, %Y %I:%M %p')}",
        f"Ends: {local_end.strftime('%b %d, %Y %I:%M %p')}",
        f"Quantity: {snapshot['quantity']}",
        f"Total Paid: NPR {Decimal(snapshot['total_amount'])}",
        f"Order ID: {snapshot['purchase_order_id']}",
        f"Transaction ID: {snapshot['transaction_id']}",
        f"Purchased At: {local_purchase_time.strftime('%b %d, %Y %I:%M %p')}",
        "",
        "Thank you,",
        "EventMandu team",
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
        font_size=11,
        color=colors.HexColor("#183153"),
        leading=13,
    )


def _format_money(amount):
    return f"NPR {Decimal(amount):,.2f}"


def _draw_section_header(pdf, title, x, y, width):
    pdf.setFillColor(colors.HexColor("#163258"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(x, y, title)
    return y - 14


def _build_reportlab_ticket_pdf(purchase, purchase_snapshot=None):
    context = build_ticket_context(purchase, purchase_snapshot=purchase_snapshot)
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

    header_height = 118
    header_y = top_y - header_height
    pdf.setFillColor(colors.HexColor("#1f6bff"))
    pdf.roundRect(card_x, header_y, card_width, header_height, 18, stroke=0, fill=1)
    pdf.rect(card_x, header_y, card_width, header_height - 18, stroke=0, fill=1)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(card_x + 24, top_y - 46, context["brand_name"])
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.HexColor("#dce8ff"))
    pdf.drawString(card_x + 24, top_y - 60, "Event ticket invoice")

    right_x = card_x + card_width - 220
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(right_x, top_y - 34, "BOOKING ID")
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawRightString(card_x + card_width - 24, top_y - 50, context["booking_id"])

    badge_w = 82
    badge_h = 24
    badge_right = card_x + card_width - 24
    badge_left = badge_right - badge_w
    badge_y = top_y - 80
    pdf.setFillColor(colors.white)
    pdf.roundRect(badge_left, badge_y, badge_w, badge_h, 12, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor(context["status_color"]))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(badge_left + (badge_w / 2), badge_y + 8, context["status_label"])

    pdf.setFillColor(colors.HexColor("#e7efff"))
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(card_x + card_width - 24, top_y - 96, f"Booked on {context['booking_date'].strftime('%b %d, %Y at %I:%M %p')}")

    content_left = card_x + 24
    content_width = card_width - 48
    footer_base_y = card_y + 20
    y = header_y - 14

    pdf.setFillColor(colors.HexColor("#3275ff"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(content_left, y, "YOUR EVENT PASS")
    y -= 22

    pdf.setFillColor(colors.HexColor("#162d50"))
    pdf.setFont("Helvetica-Bold", 20)
    event_lines = simpleSplit(context["event_name"], "Helvetica-Bold", 20, content_width)
    for line in event_lines[:2]:
        pdf.drawString(content_left, y, line)
        y -= 24

    pdf.setFillColor(colors.HexColor("#e9f1ff"))
    pdf.roundRect(content_left, y - 2, 86, 20, 10, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#205bd8"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(content_left + 10, y + 5, context["event_type"])
    y -= 18

    y = _draw_section_header(pdf, "Event Details", content_left, y, content_width)

    y = _draw_label_value(
        pdf,
        "Location",
        f"{context['venue_name']}, {context['venue_city']}, {context['venue_address']}",
        content_left,
        y,
        content_width,
    ) - 10
    y = _draw_label_value(
        pdf,
        "Date",
        context["event_end"].strftime("%b %d, %Y"),
        content_left,
        y,
        content_width,
    ) - 8

    pdf.setStrokeColor(colors.HexColor("#cfdbeb"))
    pdf.line(content_left, y, content_left + content_width, y)
    y -= 20

    y = _draw_section_header(pdf, "User Details", content_left, y, content_width)

    y = _draw_label_value(pdf, "Name", context["attendee_name"], content_left, y, content_width) - 10
    y = _draw_label_value(pdf, "Phone Number", context["attendee_phone"], content_left, y, content_width) - 10
    y = _draw_label_value(pdf, "Email", context["attendee_email"], content_left, y, content_width) - 8

    pdf.setStrokeColor(colors.HexColor("#cfdbeb"))
    pdf.line(content_left, y, content_left + content_width, y)
    y -= 20

    y = _draw_section_header(pdf, "Ticket Details", content_left, y, content_width)

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

    y -= 28
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
    y -= 12
    pdf.setStrokeColor(colors.HexColor("#cfdbeb"))
    pdf.line(content_left, y, card_x + card_width - 24, y)

    panel_y = y - 26
    panel_width = card_width - 48
    heading_bar_height = 20
    panel_content_height = 64
    heading_bar_y = panel_y
    pdf.setFillColor(colors.HexColor("#edf4ff"))
    pdf.roundRect(content_left, heading_bar_y, panel_width, heading_bar_height, 10, stroke=0, fill=1)

    panel_top = heading_bar_y + 5
    right_value_x = card_x + card_width - 38

    pdf.setFillColor(colors.HexColor("#163258"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(content_left + 14, panel_top, "Payment Summary")

    first_row_y = heading_bar_y - 18
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.drawString(content_left + 14, first_row_y, "SUBTOTAL")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(colors.HexColor("#183153"))
    pdf.drawRightString(right_value_x, first_row_y, _format_money(context["subtotal"]))

    second_row_y = first_row_y - 18
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.drawString(content_left + 14, second_row_y, "TOTAL AMOUNT")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.setFillColor(colors.HexColor("#1657df"))
    pdf.drawRightString(right_value_x, second_row_y, _format_money(context["total_amount"]))

    third_row_y = second_row_y - 18
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.drawString(content_left + 14, third_row_y, "STATUS")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors.HexColor(context["status_color"]))
    pdf.drawString(content_left + 60, third_row_y, context["status_label"])
    pdf.setFillColor(colors.HexColor("#7186a0"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(content_left + 160, third_row_y, "TXN ID")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.HexColor("#183153"))
    txn_text = str(context["transaction_id"])
    txn_lines = simpleSplit(txn_text, "Helvetica", 10, right_value_x - (content_left + 200))
    if txn_lines:
        pdf.drawString(content_left + 200, third_row_y, txn_lines[0])

    pdf.setStrokeColor(colors.HexColor("#dce6f3"))
    footer_line_y = panel_y - panel_content_height - 10
    min_footer_line_y = footer_base_y + 34
    if footer_line_y < min_footer_line_y:
        footer_line_y = min_footer_line_y
    pdf.line(content_left, footer_line_y, card_x + card_width - 24, footer_line_y)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(colors.HexColor("#5f738f"))
    pdf.drawString(content_left, footer_line_y - 18, "This is a digitally generated ticket.")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(content_left, footer_line_y - 30, f"Support: {context['support_email']} | {context['support_phone']}")
    pdf.drawString(content_left, footer_line_y - 42, "Terms: non-refundable. Please show this ticket or QR at entry if requested by the organizer.")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_ticket_pdf(purchase, purchase_snapshot=None):
    return _build_reportlab_ticket_pdf(purchase, purchase_snapshot=purchase_snapshot)


def send_ticket_email(purchase, purchase_snapshot=None):
    recipient = purchase.user.email
    if not recipient:
        return False

    email = EmailMessage(
        subject="event tickets from eventmandu",
        body=_build_ticket_email_body(purchase, purchase_snapshot=purchase_snapshot),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    email.attach(
        f"eventmandu-ticket-{purchase.purchase_order_id}.pdf",
        build_ticket_pdf(purchase, purchase_snapshot=purchase_snapshot),
        "application/pdf",
    )
    email.send(fail_silently=False)
    return True
