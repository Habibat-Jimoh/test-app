from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from siteV2.fetch_data import load_data_from_airtable
import json
import os
from datetime import datetime
from collections import defaultdict

app = FastAPI()
app.mount("/static", StaticFiles(directory="siteV2/static"), name="static")
templates = Jinja2Templates(directory="siteV2/templates")

full_data = load_data_from_airtable()

country_data = full_data.get("countries", {})
democracy_data = full_data.get("democracy", {})

# Organize democracy pages into categories
def categorize_democracy_pages():
    tracker_pages = {}
    data_pages = {}
    directory_pages = {}

    for key, page in democracy_data.items():
        # Grab category from the page_fields first
        category = page.get("page_fields", {}).get("Category", "").strip()
        
        # If not found in page_fields, try the first tab's tab_fields
        if not category and page.get("tabs"):
            tab_fields = page["tabs"][0].get("tab_fields", {})
            category = tab_fields.get("Category", "").strip()

        if category == "Election Tracker":
            tracker_pages[key] = page
        elif category == "Democracy Data":
            data_pages[key] = page
        elif category == "Directory of Country Resources":
            directory_pages[key] = page

    # Sort pages by their Order-tab (convert to int for proper numerical sorting)
    sorted_tracker_pages = dict(sorted(tracker_pages.items(), 
                                      key=lambda item: int(item[1]["tabs"][0]["tab_fields"].get("TabOrder", "0"))))
    sorted_data_pages = dict(sorted(data_pages.items(), 
                                    key=lambda item: int(item[1]["tabs"][0]["tab_fields"].get("TabOrder", "0"))))
    sorted_directory_pages = dict(sorted(directory_pages.items(), 
                                         key=lambda item: int(item[1]["tabs"][0]["tab_fields"].get("TabOrder", "0"))))

    return sorted_tracker_pages, sorted_data_pages, sorted_directory_pages

def organize_sections_by_year(subtab):
    year_groups = defaultdict(list)
    all_years = set()

    for section in subtab["sections"]:
        year = section.get("Year")
        if year:
            all_years.add(str(year))

    sorted_years = sorted(all_years, reverse=True)
    if not sorted_years:
        sorted_years = ['all']

    # Sort sections by SectionOrder (convert to int for proper numerical sorting)
    sorted_sections = sorted(subtab["sections"], 
                             key=lambda section: int(section.get("SectionOrder", "0")))

    for section in sorted_sections:
        year = section.get("Year")
        if year:
            year_groups[str(year)].append(section)
        else:
            for y in sorted_years:
                year_groups[y].append(section)

    return sorted_years, year_groups

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    tracker_pages, data_pages, directory_pages = categorize_democracy_pages()
    # Default to Upcoming Elections page
    if tracker_pages:
        first_tracker_slug = next(iter(tracker_pages))
        return RedirectResponse(url=f"/{first_tracker_slug}")
    return templates.TemplateResponse("base.html", {
        "request": request,
        "sidebar": {
            "tracker": tracker_pages,
            "democracy": data_pages,
            "countries": country_data,
            "directory": directory_pages
        },
        "year": datetime.now().year
    })

@app.get("/{slug}", response_class=HTMLResponse)
async def render_page(request: Request, slug: str):
    tracker_pages, data_pages, directory_pages = categorize_democracy_pages()
    source = (
        country_data.get(slug)
        or democracy_data.get(slug)
    )
    if not source:
        return HTMLResponse("Page not found", status_code=404)

    # Get the category to determine template behavior
    category = source["page_fields"].get("Category")
    if not category and source.get("tabs"):
        category = source["tabs"][0].get("tab_fields", {}).get("Category", "")

    country_name = source["page_fields"].get("Country")
    democracy_title = source["page_fields"].get("Democracy-page")

    # Detect if this is a Country Data & History page by presence of Country but no Category
    is_country_page = bool(country_name) and not bool(category)

    if country_name:
        page_title = f"Democracy in {country_name}"
    elif category == "Election Tracker":
        page_title = "African Election Tracker"
    elif category == "Democracy Data":
        page_title = "African Democracy Data"
    elif category == "Directory of Country Resources":
        page_title = "Directory"
    else:
        page_title = democracy_title or slug.replace("-", " ").capitalize()

    # Sort tabs by TabOrder
    sorted_tabs = sorted(source["tabs"], 
                         key=lambda tab: int(tab["tab_fields"].get("TabOrder", "0")))

    # Build structured tabs with subtabs and sections grouped by year
    structured_tabs = []
    for tab in sorted_tabs:
        tab_title = tab["tab_fields"].get("TabTitle") or tab["tab_fields"].get("Democracy-tab")
        tab_text = tab["tab_fields"].get("TabText", "") 
        more_info = tab["tab_fields"].get("More info about this page", "")

        # Dynamically generate more_info for specific country tabs if blank
        if is_country_page and not more_info:
            if tab_title == "Context & History":
                more_info = (
                    f"This page offers a comprehensive overview of {country_name}'s government and political history "
                    f"through two key interactive visualisations. The first section provides a detailed table showcasing "
                    f"vital political and economic indicators, such as {country_name}'s population, GDP, government "
                    f"structure, age and tenure of the current president, military regime status, and democracy metrics. <br><br>"
                    f"The second section presents a historical and political chronology of {country_name}, highlighting "
                    f"significant milestones such as independence, referendum history, coups, notable wars, and "
                    f"democratic progress. Together, these visualisations provide a rich resource for understanding "
                    f"{country_name}'s governance, leadership, and democratic evolution, catering to researchers, "
                    f"policymakers, and anyone interested in African political history."
                )
            elif tab_title == "Candidates":
                more_info = (
                    f"Learn more detailed information about {country_name}'s presidential candidates, including key data "
                    f"on their backgrounds, political alignments, and government experiences. Discover essential "
                    f"information about each candidate's political journey, their affiliation (independent or party-based), "
                    f"gender, and previous government roles, to deepen your understanding of the country's evolving "
                    f"leadership within African governance and democracy."
                )

        # Sort subtabs by SubtabOrder
        sorted_subtabs = sorted(tab["subtabs"], 
                                key=lambda subtab: int(subtab["subtab_fields"].get("SubtabOrder", "0")))

        subtabs = []
        for subtab in sorted_subtabs:
            subtab_title = subtab["subtab_fields"].get("SubtabTitle")
            subtab_text  = subtab["subtab_fields"].get("SubtabText")

            years, sections_by_year = organize_sections_by_year(subtab)
            subtabs.append({
                "title": subtab_title,
                "text":  subtab_text,  
                "years": years,
                "sections_by_year": sections_by_year,
                "democracy_description": subtab["subtab_fields"].get("Description")
            })
        structured_tabs.append({"title": tab_title, "text": tab_text, "more_info": more_info, "subtabs": subtabs})

    return templates.TemplateResponse("country.html", {
        "request": request,
        "page_title": page_title,
        "country_description": source["page_fields"].get("Text"),
        "source_tabs": structured_tabs,
        "category": category,
        "current_slug": slug,
        "sidebar": {
            "tracker": tracker_pages,
            "democracy": data_pages,
            "countries": country_data,
            "directory": directory_pages
        },
        "year": datetime.now().year,
        "version": datetime.now().timestamp(),
        "is_country_page": is_country_page

    })
