"""Billing: invoices and manually recorded payments (amounts stored in minor units, KES). No card data is handled or stored."""
from flask import abort, flash, g, redirect, render_template, request, url_for
from .audit import audit
from .db import insert, many, now, one, run
from .helpers import field, fmt_money, get_or_404, money_to_minor, valid_date
from .rbac import staff_required
from .staff import bp
import secrets

METHODS = ["cash", "mpesa_manual", "bank_transfer", "card_machine"]

def with_balance(inv):
    paid = one("SELECT COALESCE(SUM(amount_minor),0) AS s FROM payments WHERE invoice_id=?", (inv["id"],))["s"]
    return dict(inv, paid=paid, balance=inv["amount_minor"] - paid)

def refresh_status(inv_id):
    inv = with_balance(get_or_404("invoices", inv_id))
    if inv["status"] == "void": return
    status = "paid" if inv["balance"] <= 0 else ("part_paid" if inv["paid"] > 0 else "issued")
    run("UPDATE invoices SET status=? WHERE id=?", (status, inv_id))

@bp.get("/billing")
@staff_required("billing.read")
def billing():
    rows = [with_balance(r) for r in many("SELECT i.*, p.full_name FROM invoices i JOIN patients p ON p.id=i.patient_id ORDER BY i.id DESC LIMIT 200")]
    audit("billing.listed"); return render_template("billing.html", rows=rows, money=fmt_money)

@bp.get("/invoices/<int:iid>")
@staff_required("billing.read")
def invoice(iid):
    inv = with_balance(get_or_404("invoices", iid)); audit("invoice.viewed", target=("invoice", iid))
    return render_template("invoice.html", inv=inv, p=get_or_404("patients", inv["patient_id"]), payments=many("SELECT * FROM payments WHERE invoice_id=? ORDER BY id", (iid,)), money=fmt_money, methods=METHODS)

@bp.post("/patients/<int:pid>/invoices")
@staff_required("billing.write")
def invoice_new(pid):
    get_or_404("patients", pid); desc, amount, due = field("description", 200), money_to_minor(field("amount", 20)), field("due_date", 10)
    if not desc or amount is None or (due and not valid_date(due)): flash("Enter a description, an amount greater than zero (two decimals at most) and, if used, a due date as YYYY-MM-DD.", "error"); return redirect(url_for("staff.patient", pid=pid))
    iid = insert("INSERT INTO invoices (patient_id, number, description, amount_minor, issued_at, due_date, created_by) VALUES (?,?,?,?,?,?,?)", (pid, "INV-" + secrets.token_hex(4).upper(), desc, amount, now(), due or None, g.staff["id"]))
    audit("invoice.created", target=("invoice", iid), detail={"patient_id": pid, "amount_minor": amount}); return redirect(url_for("staff.invoice", iid=iid))

@bp.post("/invoices/<int:iid>/payments")
@staff_required("billing.write")
def payment_add(iid):
    inv = with_balance(get_or_404("invoices", iid)); amount, method = money_to_minor(field("amount", 20)), field("method", 20)
    if inv["status"] == "void": flash("This invoice is void.", "error")
    elif amount is None or method not in METHODS: flash("Enter a valid amount and payment method.", "error")
    elif amount > inv["balance"]: flash("The payment is more than the outstanding balance.", "error")
    else:
        pid_ = insert("INSERT INTO payments (invoice_id, amount_minor, method, reference, received_at, recorded_by) VALUES (?,?,?,?,?,?)", (iid, amount, method, field("reference", 80) or None, now(), g.staff["id"]))
        refresh_status(iid); audit("payment.recorded", target=("payment", pid_), detail={"invoice_id": iid, "amount_minor": amount, "method": method})
    return redirect(url_for("staff.invoice", iid=iid))

@bp.post("/invoices/<int:iid>/void")
@staff_required("billing.write")
def invoice_void(iid):
    inv = with_balance(get_or_404("invoices", iid))
    if inv["paid"] > 0: flash("An invoice with payments cannot be voided.", "error")
    else: run("UPDATE invoices SET status='void' WHERE id=?", (iid,)); audit("invoice.voided", target=("invoice", iid))
    return redirect(url_for("staff.invoice", iid=iid))
