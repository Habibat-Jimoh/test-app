import os
import json
from typing import Dict, Any
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

def extract_country_data(base) -> Dict[str, Any]:
    pages = base.table("Pages").all()
    tabs = base.table("Tabs").all()
    subtabs = base.table("Subtabs").all()
    sections = base.table("Sections").all()

    tab_lookup = {t["id"]: t for t in tabs}
    subtab_lookup = {s["id"]: s for s in subtabs}
    section_lookup = {s["id"]: s for s in sections}

    result = {}

    for page in pages:
        fields = page["fields"]
        if not fields.get("PublishStatus"):
            continue

        page_id = fields.get("PageID")
        tab_ids = fields.get("TabID", [])
        country_data = {"page_fields": fields.copy(), "tabs": []}

        for tab_id in tab_ids:
            tab = tab_lookup.get(tab_id)
            if not tab or not tab["fields"].get("PublishStatus"):
                continue

            tab_fields = tab["fields"]
            subtab_ids = tab_fields.get("SubtabID", [])
            tab_data = {"tab_fields": tab_fields.copy(), "subtabs": []}

            for subtab_id in subtab_ids:
                subtab = subtab_lookup.get(subtab_id)
                if not subtab or not subtab["fields"].get("SubtabShow"):
                    continue

                subtab_fields = subtab["fields"]
                section_ids = subtab_fields.get("SectionID", [])
                subtab_data = {"subtab_fields": subtab_fields.copy(), "sections": []}


                for section_id in section_ids:
                    section = section_lookup.get(section_id)
                    if not section or section["fields"].get("ShowSection") != "Yes":
                        continue

                    section_data = section["fields"].copy()
                    subtab_data["sections"].append(section_data)

                tab_data["subtabs"].append(subtab_data)

            country_data["tabs"].append(tab_data)

        result[page_id] = country_data

    return result


def extract_democracy_data(base) -> Dict[str, Any]:
    pages = base.table("Democracy-pages").all()
    tabs = base.table("Democracy-tabs").all()
    subtabs = base.table("Democracy-subtabs").all()
    sections = base.table("Democracy-sections").all()

    tab_lookup = {t["id"]: t for t in tabs}
    subtab_lookup = {s["id"]: s for s in subtabs}

    subtab_id_to_sections = {}
    for section in sections:
        fields = section["fields"]
        subtab_id = fields.get("Democracy-subtabID")
        if not subtab_id:
            continue
        if isinstance(subtab_id, list):
            for sid in subtab_id:
                subtab_id_to_sections.setdefault(sid, []).append(section)
        else:
            subtab_id_to_sections.setdefault(subtab_id, []).append(section)

    result = {}

    for page in pages:
        fields = page["fields"]
        page_id = fields.get("Democracy-pageID")
        tab_ids = fields.get("Democracy-tabID", [])
        page_data = {"page_fields": fields.copy(), "tabs": []}

        for tab_id in tab_ids:
            tab = tab_lookup.get(tab_id)
            if not tab:
                continue

            tab_fields = tab["fields"]
            tab_data = {"tab_fields": tab_fields.copy(), "subtabs": []}

            for subtab in subtabs:
                subtab_fields = subtab["fields"]
                if tab_id not in subtab_fields.get("Democracy-tabID", []):
                    continue

                subtab_id = subtab["id"]
                subtab_data = {"subtab_fields": subtab_fields.copy(), "sections": []}

                for section in subtab_id_to_sections.get(subtab_id, []):
                    subtab_data["sections"].append(section["fields"].copy())

                tab_data["subtabs"].append(subtab_data)

            page_data["tabs"].append(tab_data)

        result[page_id] = page_data

    return result


def load_data_from_airtable() -> None:
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")

    if not all([api_key, base_id]):
        raise ValueError("Missing API credentials")

    api = Api(api_key)
    base = api.base(base_id)

    print("Fetching Airtable data")

    countries = extract_country_data(base)
    democracy = extract_democracy_data(base)

    combined = {"countries": countries, "democracy": democracy}
    os.makedirs("data", exist_ok=True)
    with open("siteV2/data/africa_pages.json", "w") as f:
        json.dump(combined, f, indent=2)

    print("Data written to africa_pages.json")
    return combined


if __name__ == "__main__":
    load_data_from_airtable()
