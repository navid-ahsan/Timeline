from typing import TypedDict, Annotated, Literal
import operator
from pydantic import BaseModel, Field


EventType = Literal[
    "ehkaiseva_lastensuojelu",
    "lastensuojeluilmoitus",
    "lastensuojelutarpeen_selvitys",
    "asiakkuuden_alkaminen",
    "avohuollon_tukitoimet",
    "kiireellinen_sijoitus",
    "huostaanotto",
    "sijaishuolto_perhehoito",
    "sijaishuolto_laitoshoito",
    "sijaishuoltopaikan_muutos",
    "jalkihuolto",
    "psykiatrinen_hoito",
    "perhevakivalta_epaily",
    "paihdekaytto",
    "rikosepaily",
    "koulupoissaolot_vakavat",
    "muu_kriittinen",
]


class LifeEvent(BaseModel):
    date: str
    event_type: EventType
    description: str
    severity: int = Field(ge=1, le=5)
    source_document: str
    legal_basis: str


class PatientState(TypedDict):
    # Persistent — accumulates across sessions
    patient_id: str
    all_events: Annotated[list, operator.add]
    processed_documents: Annotated[list, operator.add]

    # Updated each session
    top_10_timeline: list
    last_updated: str

    # Session-specific
    current_documents: list
    new_events: Annotated[list, operator.add]
    retry_count: int
    human_approved: bool
    eval_passed: bool
