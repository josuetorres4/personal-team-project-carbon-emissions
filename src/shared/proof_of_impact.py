"""
Proof-of-Impact Layer — generates CSRD-grade evidence cards.
Every verified saving gets an auditable one-page report.
"""
from fpdf import FPDF
from datetime import datetime
from pathlib import Path


class ProofOfImpactCard:
    """One-page auditable evidence card per verified saving."""

    def __init__(self, verification: dict, job: dict, market: dict):
        self.v = verification
        self.j = job
        self.m = market
        self.generated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        """Machine-readable evidence record."""
        saving_kg = self.v.get("point_estimate_kg", 0) or 0
        return {
            "evidence_id": f"POI-{self.j.get('job_id', 'unknown')}",
            "generated_at": self.generated_at,
            "job_id": self.j.get("job_id"),
            "team": self.j.get("team"),
            "action_taken": self.v.get("action"),
            "carbon_saving_kg": saving_kg,
            "carbon_saving_tonnes": round(saving_kg / 1000, 6),
            "ci_lower_kg": self.v.get("ci_lower_kg"),
            "ci_upper_kg": self.v.get("ci_upper_kg"),
            "saving_is_significant": self.v.get("saving_is_significant"),
            "ci_method": self.v.get("method", "bootstrap"),
            "data_source": self.v.get("carbon_data_source", "unknown"),
            "is_real_data": self.v.get("is_real", False),
            "counterfactual_description": (
                f"Job would have emitted {self.v.get('counterfactual_kg', 0):.3f} kg CO2e "
                f"at original schedule. Actual: {self.v.get('actual_kg', 0):.3f} kg CO2e."
            ),
            "plain_english_verdict": self._verdict(),
            "csrd_scope": "Scope 2 - cloud compute",
            "ghg_protocol_method": "Location-based",
            "auditor_note": (
                "Confidence interval computed via bootstrap resampling of realized "
                "carbon intensity values. Saving is statistically significant if "
                "entire CI is positive (zero excluded)."
            )
        }

    def _verdict(self) -> str:
        if not self.v.get("saving_is_significant"):
            return "Saving not statistically significant -- CI crosses zero. Do not claim this in CSRD report."
        kg = self.v.get("point_estimate_kg", 0) or 0
        if kg > 100:
            return f"Strong verified saving of {kg:.1f} kg CO2e. Suitable for CSRD Scope 2 disclosure."
        return f"Verified saving of {kg:.1f} kg CO2e. Suitable for CSRD Scope 2 disclosure."

    def to_pdf(self, output_path: str):
        """Generate a one-page PDF evidence card."""
        d = self.to_dict()
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Carbon Saving Evidence Card", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, f"Evidence ID: {d['evidence_id']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Generated: {d['generated_at']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Team: {d['team']}  |  Job: {d['job_id']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Verified Carbon Saving", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        saving_kg = d['carbon_saving_kg'] or 0
        ci_lower = d['ci_lower_kg'] or 0
        ci_upper = d['ci_upper_kg'] or 0
        pdf.cell(0, 7, f"  Point estimate: {saving_kg:.3f} kg CO2e", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, f"  95% CI: [{ci_lower:.3f}, {ci_upper:.3f}] kg CO2e", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, f"  Statistically significant: {d['saving_is_significant']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Counterfactual Analysis", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, d["counterfactual_description"])
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "CSRD / GHG Protocol Compliance", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, f"  Scope: {d['csrd_scope']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"  Method: {d['ghg_protocol_method']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"  Data source: {d['data_source']} (real: {d['is_real_data']})", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Verdict", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 7, d["plain_english_verdict"])
        pdf.ln(4)
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 5, f"Auditor note: {d['auditor_note']}")
        Path(output_path).parent.mkdir(exist_ok=True)
        pdf.output(output_path)
