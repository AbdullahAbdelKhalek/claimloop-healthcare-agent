"""The three LLM agents, built on the OpenAI Agents SDK over the Responses API.

Design choice: the pipeline order is fixed, so orchestration lives in plain
code (see orchestrator.py) and agents are used only where language
understanding is needed. Handoffs would let agents pass control to each
other, but a linear billing workflow is clearer as a loop you can read.
"""

import json

from agents import Agent, ModelSettings, function_tool

from . import config
from .cpt_reference import fee_schedule_text
from .icd_lookup import search_terms
from .payer import grant_prior_auth
from .schemas import (
    AdjudicationResult,
    Claim,
    CodingResult,
    EncounterNote,
    ResolutionDecision,
)


# ------------------------------------------------------------------- tools

@function_tool
def search_icd10(query: str) -> str:
    """Search the official ICD-10-CM code table by clinical term or by code.

    Args:
        query: A clinical term such as "knee osteoarthritis" or a code
            fragment such as "M17". Returns a JSON list of {code, name}.
    """
    return json.dumps(search_terms(query))


@function_tool
def request_prior_auth(cpt_code: str, icd10_codes: list[str]) -> str:
    """Request prior authorization from the payer portal for one CPT code.

    Args:
        cpt_code: The procedure code that needs authorization.
        icd10_codes: The diagnosis codes that justify the procedure.
    """
    auth = grant_prior_auth(cpt_code, icd10_codes)
    if auth:
        return json.dumps({"status": "approved", "auth_number": auth,
                           "note": "Attach this number to the service line and resubmit."})
    return json.dumps({"status": "denied",
                       "reason": "Payer criteria not met for the given diagnosis codes."})


# ------------------------------------------------------------ agent factory

def _model_settings() -> ModelSettings | None:
    try:
        from openai.types.shared import Reasoning
        return ModelSettings(reasoning=Reasoning(effort=config.REASONING_EFFORT))
    except Exception:
        return None


def _agent(name: str, instructions: str, output_type, tools=None, cheap: bool = False) -> Agent:
    kwargs = {
        "name": name,
        "instructions": instructions,
        "model": config.MODEL_CHEAP if cheap else config.MODEL_MAIN,
        "output_type": output_type,
    }
    if tools:
        kwargs["tools"] = tools
    settings = _model_settings()
    if settings is not None:
        kwargs["model_settings"] = settings
    return Agent(**kwargs)


SCRIBE_INSTRUCTIONS = """You are a clinical scribe. You receive the raw transcript of a
doctor-patient encounter and produce a structured visit note.

Rules:
- Use only information stated in the transcript. Never invent findings,
  history, medications, or results.
- Where a section has no information in the transcript, write "Not documented".
- Keep the language factual and concise, the way a chart note reads.
- Every problem discussed gets its own entry in assessment_and_plan."""


CODER_INSTRUCTIONS_TEMPLATE = """You are a medical coder for an outpatient clinic. You receive a
structured visit note and produce billing codes.

Diagnosis coding rules:
- Suggest ICD-10-CM codes for the documented problems.
- You MUST verify every code with the search_icd10 tool before including it.
  Only include codes the tool confirms exist. Prefer the most specific
  billable code the documentation supports.
- Do not code conditions that are merely historical unless they were
  addressed during the visit.

Procedure coding rules:
- You may ONLY use CPT codes from this payer fee schedule:

{fee_schedule}

- Include exactly one office visit evaluation and management code, chosen
  conservatively from the documentation.
- Include procedure or lab codes only when the note documents that the
  service was performed or ordered at this visit.
- dx_pointers holds 1-based positions into your diagnosis list, linking each
  procedure to the diagnoses that justify it.
- Set confidence between 0 and 1 honestly. Explain doubts in coding_notes."""


RESOLVER_INSTRUCTIONS = """You are a claims denial specialist. A claim you are responsible for
was denied. You receive the visit note, the coding that was billed, the claim,
and the payer's adjudication with CARC/RARC denial codes.

Decide one action:
- fix_and_resubmit: correct the coding or claim fields and try again.
- appeal: when you believe the documentation already supports the billed
  services and the denial is wrong. Write a short professional appeal letter
  that cites the specific documentation.
- abandon: when the denial is correct and no compliant fix exists.

Rules:
- Never invent clinical facts. Fixes must be supported by the visit note.
- CARC 197 (authorization absent): use the request_prior_auth tool. If it is
  approved, keep the procedure and add a field fix with field
  "prior_auth:<cpt_code>" and the auth number as the value. If it is denied,
  remove or replace the procedure.
- CARC 50 (not medically necessary): first check whether a documented
  diagnosis better supports the procedure (verify codes with search_icd10).
  If the documentation truly supports the service but the linked codes were
  wrong, fix the pointers or diagnoses. Appeal only when coding is already
  correct.
- CARC 150 (level of service not supported): downcode the office visit or,
  if the note genuinely documents additional distinct problems, add the
  missing diagnoses. Never upcode.
- CARC 146 or 181 (invalid codes): replace with valid codes, verified by tool.
- CARC 16 (missing information): supply the missing field via field_fixes.
- Always return the complete revised diagnosis and procedure lists, not a
  diff, even for an appeal (return them unchanged in that case)."""


def build_scribe(cheap: bool = False) -> Agent:
    return _agent("Scribe", SCRIBE_INSTRUCTIONS, EncounterNote, cheap=cheap)


def build_coder(cheap: bool = False) -> Agent:
    instructions = CODER_INSTRUCTIONS_TEMPLATE.format(fee_schedule=fee_schedule_text())
    return _agent("Coder", instructions, CodingResult, tools=[search_icd10], cheap=cheap)


def build_resolver(cheap: bool = False) -> Agent:
    return _agent("DenialResolver", RESOLVER_INSTRUCTIONS, ResolutionDecision,
                  tools=[search_icd10, request_prior_auth], cheap=cheap)


def resolver_input(note: EncounterNote, coding: CodingResult, claim: Claim,
                   adjudication: AdjudicationResult) -> str:
    return (
        "VISIT NOTE\n" + note.to_text()
        + "\n\nCODING AS BILLED\n" + coding.model_dump_json(indent=2)
        + "\n\nCLAIM\n" + claim.model_dump_json(indent=2)
        + "\n\nPAYER ADJUDICATION\n" + adjudication.model_dump_json(indent=2)
    )
