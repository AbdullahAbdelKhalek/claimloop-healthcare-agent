"""The mock payer: a deterministic rules engine that adjudicates claims.

This is the environment the agents work against, not a dataset and not an
LLM. Every rule is ordinary code so denials are reproducible and the
evaluation can measure exactly which denial categories the resolution agent
can fix. Denials use real public CARC and RARC code numbers maintained by
X12, with paraphrased descriptions.
"""

import zlib

from .cpt_reference import (
    EM_CODES,
    EM_MIN_DIAGNOSES,
    FEE_SCHEDULE,
    MEDICAL_NECESSITY,
    PRIOR_AUTH_REQUIRED,
)
from .icd_lookup import validate_code
from .schemas import (
    AdjudicationResult,
    AppealOutcome,
    Claim,
    DenialReason,
    LineOutcome,
)


def necessity_met(cpt_code: str, icd_codes: list[str]) -> bool:
    """True when at least one diagnosis matches the demo policy for this CPT."""
    if cpt_code in EM_CODES:
        return True
    prefixes = MEDICAL_NECESSITY.get(cpt_code, [])
    return any(code.upper().startswith(p) for code in icd_codes for p in prefixes)


def grant_prior_auth(cpt_code: str, icd10_codes: list[str]) -> str | None:
    """The payer's authorization portal. Deterministic: auth is granted when
    the demo necessity policy is satisfied, and the auth number is derived
    from the request so the adjudicator can verify it later."""
    if cpt_code not in PRIOR_AUTH_REQUIRED:
        return None
    if not necessity_met(cpt_code, icd10_codes):
        return None
    seed = cpt_code + "|" + ",".join(sorted(c.upper() for c in icd10_codes))
    return f"PA{zlib.crc32(seed.encode()) % 1_000_000:06d}"


def _deny(carc: str, description: str, rarc: str | None = None, field: str | None = None) -> DenialReason:
    return DenialReason(group="CO", carc=carc, rarc=rarc, description=description, field=field)


class MockPayer:
    """Adjudicates claims for one pipeline run. Remembers what it has seen so
    an unchanged resubmission is denied as a duplicate (CARC 18)."""

    def __init__(self) -> None:
        self._seen_fingerprints: set[str] = set()

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _fingerprint(claim: Claim) -> str:
        dx = ",".join(sorted(d.icd10_code for d in claim.diagnoses))
        lines = ",".join(
            f"{l.cpt_code}x{l.units}@{sorted(l.dx_pointers)}#{l.prior_auth_number or ''}"
            for l in sorted(claim.service_lines, key=lambda l: l.cpt_code)
        )
        return f"{claim.encounter_id}|{dx}|{lines}"

    def _claim_level_denials(self, claim: Claim) -> list[DenialReason]:
        denials: list[DenialReason] = []

        # R1 completeness
        required = {
            "patient.first_name": claim.patient.first_name,
            "patient.last_name": claim.patient.last_name,
            "patient.date_of_birth": claim.patient.date_of_birth,
            "patient.member_id": claim.patient.member_id,
            "provider.npi": claim.provider.npi,
            "service_date": claim.service_date,
        }
        for field, value in required.items():
            if not str(value).strip():
                denials.append(_deny("16", f"Claim lacks information: {field} is missing.",
                                     rarc="N382" if field.startswith("patient") else "N290",
                                     field=field))
        if not claim.diagnoses:
            denials.append(_deny("16", "Claim lacks information: no diagnosis codes present.",
                                 rarc="M76", field="diagnoses"))
        if not claim.service_lines:
            denials.append(_deny("16", "Claim lacks information: no service lines present.",
                                 field="service_lines"))

        # R2a diagnosis code validity, checked against the live ICD-10-CM table
        for dx in claim.diagnoses:
            check = validate_code(dx.icd10_code)
            if check["valid"] is False:
                denials.append(_deny("146", f"Diagnosis code {dx.icd10_code} is not a valid ICD-10-CM code.",
                                     field=f"diagnoses[{dx.sequence}]"))
        return denials

    def _line_denials(self, claim: Claim, line) -> list[DenialReason]:
        denials: list[DenialReason] = []
        dx_by_seq = {d.sequence: d.icd10_code for d in claim.diagnoses}

        # R2b procedure code on the fee schedule
        if line.cpt_code not in FEE_SCHEDULE:
            denials.append(_deny("181", f"Procedure code {line.cpt_code} is invalid or not covered by this payer."))
            return denials  # nothing else to evaluate for an unknown code

        # R1b diagnosis pointers must point at real entries
        pointed = [dx_by_seq[p] for p in line.dx_pointers if p in dx_by_seq]
        if not pointed:
            denials.append(_deny("16", f"Service line {line.cpt_code} lacks a valid diagnosis pointer.",
                                 rarc="M76", field=f"lines[{line.sequence}].dx_pointers"))
            return denials

        # R3 medical necessity
        if not necessity_met(line.cpt_code, pointed):
            denials.append(_deny("50", f"{line.cpt_code} is not deemed medically necessary "
                                       f"for the linked diagnoses ({', '.join(pointed)})."))

        # R4 prior authorization
        if line.cpt_code in PRIOR_AUTH_REQUIRED:
            expected = grant_prior_auth(line.cpt_code, pointed)
            if not line.prior_auth_number:
                denials.append(_deny("197", f"Precertification or authorization is absent for {line.cpt_code}.",
                                     rarc="N517"))
            elif line.prior_auth_number != expected:
                denials.append(_deny("197", f"The authorization number on file for {line.cpt_code} is not valid.",
                                     rarc="N517"))

        # R5 documentation support for high level office visits
        min_dx = EM_MIN_DIAGNOSES.get(line.cpt_code)
        if min_dx and len(claim.diagnoses) < min_dx:
            denials.append(_deny("150", f"Payer deems the level of service {line.cpt_code} not supported: "
                                        f"{len(claim.diagnoses)} diagnosis code(s) on the claim, "
                                        f"policy expects at least {min_dx}."))
        return denials

    # ------------------------------------------------------------- public

    def submit(self, claim: Claim) -> AdjudicationResult:
        remittance: list[str] = []

        # R6 duplicate submission check happens first
        fp = self._fingerprint(claim)
        if fp in self._seen_fingerprints:
            dup = _deny("18", "Exact duplicate of a claim already adjudicated. Change the claim before resubmitting.")
            return AdjudicationResult(
                claim_id=claim.claim_id, status="denied",
                line_outcomes=[], claim_level_denials=[dup], paid_total_cents=0,
                remittance_notes=["Duplicate submission rejected."],
            )
        self._seen_fingerprints.add(fp)

        claim_denials = self._claim_level_denials(claim)
        line_outcomes: list[LineOutcome] = []
        paid_total = 0

        for line in claim.service_lines:
            denials = self._line_denials(claim, line)
            if claim_denials:
                status = "denied"
                paid = 0
            elif denials:
                status = "denied"
                paid = 0
            else:
                status = "accepted"
                paid = FEE_SCHEDULE[line.cpt_code]["charge_cents"] * line.units
                paid_total += paid
            for d in denials:
                remittance.append(f"Line {line.sequence} ({line.cpt_code}): CO-{d.carc}"
                                  + (f" {d.rarc}" if d.rarc else "") + f". {d.description}")
            line_outcomes.append(LineOutcome(sequence=line.sequence, cpt_code=line.cpt_code,
                                             status=status, paid_cents=paid, denials=denials))

        for d in claim_denials:
            remittance.append(f"Claim: CO-{d.carc}" + (f" {d.rarc}" if d.rarc else "") + f". {d.description}")

        all_accepted = not claim_denials and all(lo.status == "accepted" for lo in line_outcomes) and line_outcomes
        status = "accepted" if all_accepted else "denied"
        if status == "accepted":
            remittance.insert(0, f"Claim accepted. Paid ${paid_total / 100:.2f}.")
        else:
            paid_total = 0

        return AdjudicationResult(
            claim_id=claim.claim_id, status=status, line_outcomes=line_outcomes,
            claim_level_denials=claim_denials, paid_total_cents=paid_total,
            remittance_notes=remittance,
        )

    def appeal(self, claim: Claim, letter: str) -> AppealOutcome:
        """First level appeal review, deterministic.

        The reviewer re-checks only medical necessity denials (CARC 50): the
        appeal succeeds when the claim's full diagnosis list, not just the
        pointed diagnoses, satisfies the necessity policy, which models a
        human reviewer reading the whole record. Other denial types are not
        appealable in this demo and are upheld.
        """
        if not letter.strip():
            return AppealOutcome(claim_id=claim.claim_id, decision="upheld",
                                 explanation="No appeal letter was provided.")
        all_dx = [d.icd10_code for d in claim.diagnoses]
        adj = self.submit_preview(claim)
        carc_set = {d.carc for lo in adj.line_outcomes for d in lo.denials} | {d.carc for d in adj.claim_level_denials}
        if carc_set != {"50"}:
            return AppealOutcome(claim_id=claim.claim_id, decision="upheld",
                                 explanation="Appeals are only reviewed for medical necessity denials in this demo.")
        fixable = all(
            necessity_met(lo.cpt_code, all_dx)
            for lo in adj.line_outcomes if any(d.carc == "50" for d in lo.denials)
        )
        if fixable:
            return AppealOutcome(claim_id=claim.claim_id, decision="overturned",
                                 explanation="On review, the documented diagnoses support the billed services. Denial overturned.")
        return AppealOutcome(claim_id=claim.claim_id, decision="upheld",
                             explanation="The documented diagnoses still do not support the billed services.")

    def submit_preview(self, claim: Claim) -> AdjudicationResult:
        """Adjudicate without recording a fingerprint, used by appeal review."""
        saved = set(self._seen_fingerprints)
        self._seen_fingerprints.discard(self._fingerprint(claim))
        try:
            return self.submit(claim)
        finally:
            self._seen_fingerprints = saved
