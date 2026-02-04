from sqlalchemy.orm import Session
from models.risk import RiskAnalysis
from models.invoice import Invoice


def upsert_risk(
    db: Session,
    *,
    invoice_pk: int,
    rate: float,
    risk_level: str,
    reasons: list,
) -> None:
    row = db.query(RiskAnalysis).filter(RiskAnalysis.invoice_id_fk == invoice_pk).first()
    if not row:
        row = RiskAnalysis(
            invoice_id_fk=invoice_pk,
            rate=rate,
            risk_level=risk_level,
            reasons=reasons,
        )
        db.add(row)
    else:
        row.rate = rate
        row.risk_level = risk_level
        row.reasons = reasons

    db.commit()


def list_anomalies(db: Session, min_rate: float = 0.6, limit: int = 300) -> list[Invoice]:
    # invoices with risk >= min_rate
    return (
        db.query(Invoice)
        .join(RiskAnalysis, RiskAnalysis.invoice_id_fk == Invoice.id)
        .filter(RiskAnalysis.rate >= min_rate)
        .order_by(RiskAnalysis.rate.desc())
        .limit(limit)
        .all()
    )
