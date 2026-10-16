"""Synthetic invoices for field extraction (labels by construction)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from data.generator.common import rng, stratified_splits

VENDOR_A = ["Brightline", "Cedar", "Harbor", "Juniper", "Kestrel", "Maple", "Orchid", "Summit", "Tidewater", "Willow"]
VENDOR_B = ["Office Supply", "Print Works", "Logistics", "Catering", "Cleaning Co", "Hardware", "Studio", "Labs"]
VENDOR_C = ["Ltd", "GmbH", "LLC", "BV", "SAS"]
CUSTOMERS = ["Pinecrest Supply", "Blue Fern Cafe", "Atlas Robotics Club", "Riverside Library"]
ITEMS = [
    "Paper ream",
    "Toner cartridge",
    "Desk organiser",
    "Cable set",
    "Lunch platter",
    "Floor cleaning",
    "Poster print",
    "Shelf bracket",
    "Label roll",
    "Notebook pack",
]
CURRENCIES = {"EUR": "€", "USD": "$", "GBP": "£"}
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _date_text(d: dt.date, style: int) -> str:
    if style == 0:
        return d.isoformat()
    if style == 1:
        return f"{d.day} {MONTHS[d.month - 1][:3]} {d.year}"
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def _money(value: float, currency: str, symbol_style: bool) -> str:
    return f"{CURRENCIES[currency]}{value:,.2f}" if symbol_style else f"{value:,.2f} {currency}"


def generate(n: int = 150, n_dev: int = 90) -> list[dict[str, Any]]:
    r = rng("extract")
    rows: list[dict[str, Any]] = []
    formats: list[str] = []
    for i in range(n):
        vendor = f"{r.choice(VENDOR_A)} {r.choice(VENDOR_B)} {r.choice(VENDOR_C)}"
        number = f"INV-{r.randint(10000, 99999)}"
        date = dt.date(2026, 1, 1) + dt.timedelta(days=r.randint(0, 270))
        currency = r.choice(list(CURRENCIES))
        symbol_style = r.random() < 0.3
        lines = []
        subtotal = 0.0
        for _ in range(r.randint(1, 4)):
            qty, price = r.randint(1, 12), round(r.uniform(2, 180), 2)
            subtotal += qty * price
            lines.append(f"- {qty} x {r.choice(ITEMS)} @ {price:.2f}")
        subtotal = round(subtotal, 2)
        tax = round(subtotal * 0.2, 2)
        total = round(subtotal + tax, 2)
        date_style = r.randint(0, 2)
        number_label = r.choice(["Invoice No:", "Invoice #:", "Invoice number"])
        hard = r.random() < 0.04
        total_label = "Please pay" if hard else r.choice(["Total due:", "TOTAL:", "Amount due:", "Balance due:"])
        body = [
            vendor,
            f"{number_label} {number}",
            f"Date: {_date_text(date, date_style)}",
            f"Bill to: {r.choice(CUSTOMERS)}",
            *lines,
            f"Subtotal: {_money(subtotal, currency, symbol_style)}",
        ]
        tax_line = f"Tax (20%): {_money(tax, currency, symbol_style)}"
        total_line = f"{total_label} {_money(total, currency, symbol_style)}"
        # Hard invoices put the payable amount before the tax line, without a "total" keyword.
        body += [total_line, tax_line] if hard else [tax_line, total_line]
        body.append(r.choice(["Payment within 30 days.", "Thank you for your business.", "Bank transfer only."]))
        fmt = f"date{date_style}"
        formats.append(fmt)
        rows.append(
            {
                "id": f"ext-{i + 1:03d}",
                "split": "",
                "input": {"document": "\n".join(body)},
                "expected": {
                    "invoice_number": number,
                    "date": date.isoformat(),
                    "total": total,
                    "currency": currency,
                    "vendor": vendor,
                },
                "tags": [fmt, "symbol" if symbol_style else "code"] + (["hard"] if hard else []),
                "meta": {"generator": "extract", "subtotal": subtotal, "tax": tax},
            }
        )
    for row, split in zip(rows, stratified_splits(formats, n_dev / n, r), strict=True):
        row["split"] = split
    return rows
