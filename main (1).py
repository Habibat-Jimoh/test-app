from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import os
from datetime import datetime
from collections import defaultdict

app = FastAPI()
app.mount("/static", StaticFiles(directory="siteV2/static"), name="static")
templates = Jinja2Templates(directory="siteV2/templates")

def load_data_from_json():
    """Load data from the saved JSON file"""
    try:
        with open("siteV2/data/africa_pages.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("JSON data file not found. Please run fetch_data.py to generate it.")
        return {"countries": {}, "democracy": {}}
    except json.JSONDecodeError:
        print("Error reading JSON data file.")
        return {"countries": {}, "democracy": {}}

full_data = load_data_from_json()

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
    sorted_tracker_pages = dict(
        sorted(tracker_pages.items(),
               key=lambda item: int(item[1]["tabs"][0]["tab_fields"].get(
                   "TabOrder", "0"))))
    sorted_data_pages = dict(
        sorted(data_pages.items(),
               key=lambda item: int(item[1]["tabs"][0]["tab_fields"].get(
                   "TabOrder", "0"))))
    sorted_directory_pages = dict(
        sorted(directory_pages.items(),
               key=lambda item: int(item[1]["tabs"][0]["tab_fields"].get(
                   "TabOrder", "0"))))

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
    sorted_sections = sorted(
        subtab["sections"],
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
    # Sort countries alphabetically by country name
    sorted_countries = dict(sorted(
        country_data.items(),
        key=lambda item: item[1]["page_fields"].get("Country", "").lower()
    ))
    # Default to Upcoming Elections page
    if tracker_pages:
        first_tracker_slug = next(iter(tracker_pages))
        return RedirectResponse(url=f"/{first_tracker_slug}")
    return templates.TemplateResponse(
        "base.html", {
            "request": request,
            "sidebar": {
                "tracker": tracker_pages,
                "democracy": data_pages,
                "countries": sorted_countries,
                "directory": directory_pages
            },
            "year": datetime.now().year
        })


@app.get("/sitemap.xml", response_class=Response)
async def sitemap(request: Request):
    from .sitemap import generate_sitemap
    sitemap_xml = generate_sitemap(request)
    return Response(content=sitemap_xml, media_type="application/xml")


@app.get("/robots.txt", response_class=Response)
async def robots_txt():
    with open("siteV2/static/robots.txt", "r") as f:
        content = f.read()
    return Response(content=content, media_type="text/plain")


@app.get("/{hyphenated_url}", response_class=HTMLResponse)
async def render_hyphenated_url(request: Request, hyphenated_url: str):
    # First check if it's a simple slug (no hyphens connecting parts)
    if hyphenated_url in country_data or hyphenated_url in democracy_data:
        return await render_simple_page(request, hyphenated_url)

    # Parse hyphenated URL format: country-tab-slug-year or country-tab-slug
    # Handle double hyphens by temporarily replacing them
    temp_url = hyphenated_url.replace('--', '__DOUBLE_HYPHEN__')
    parts = temp_url.split('-')

    # Try to extract year from the end
    year = None
    if len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) == 4:
        year = parts[-1]
        parts = parts[:-1]

    # Find the longest matching country slug by trying from longest to shortest
    country_slug = None
    tab_slug = None

    # Try from longest possible country name to shortest
    for i in range(len(parts), 0, -1):
        potential_country = '-'.join(parts[:i]).replace('__DOUBLE_HYPHEN__', '--')
        if potential_country in country_data or potential_country in democracy_data:
            country_slug = potential_country
            if i < len(parts):
                tab_slug = '-'.join(parts[i:]).replace('__DOUBLE_HYPHEN__', '--')
            break

    if not country_slug:
        return HTMLResponse("Page not found", status_code=404)

    return await render_tab_page_with_year(request, country_slug, tab_slug, year)

async def render_simple_page(request: Request, slug: str):
    tracker_pages, data_pages, directory_pages = categorize_democracy_pages()
    sorted_countries = dict(sorted(
        country_data.items(),
        key=lambda item: item[1]["page_fields"].get("Country", "").lower()
    ))
    source = (country_data.get(slug) or democracy_data.get(slug))
    if not source:
        return HTMLResponse("Page not found", status_code=404)

    # For pages with multiple tabs, redirect to first tab
    if source.get("tabs") and len(source["tabs"]) > 1:
        sorted_tabs = sorted(
            source["tabs"],
            key=lambda tab: int(tab["tab_fields"].get("TabOrder", "0")))
        first_tab = sorted_tabs[0]
        tab_title = first_tab["tab_fields"].get("TabTitle") or first_tab["tab_fields"].get("Democracy-tab")
        tab_slug = tab_title.lower().replace(" ", "-").replace("&", "").replace("  ", "-")
        hyphenated_url = f"{slug}-{tab_slug}"
        return RedirectResponse(url=f"/{hyphenated_url}")

    # Single tab pages - render directly
    return await render_tab_page_with_year(request, slug, None, None)

async def render_tab_page_with_year(request: Request, slug: str, tab_slug: str = None, year: str = None):
    tracker_pages, data_pages, directory_pages = categorize_democracy_pages()
    sorted_countries = dict(sorted(
        country_data.items(),
        key=lambda item: item[1]["page_fields"].get("Country", "").lower()
    ))
    source = (country_data.get(slug) or democracy_data.get(slug))
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
    sorted_tabs = sorted(
        source["tabs"],
        key=lambda tab: int(tab["tab_fields"].get("TabOrder", "0")))

    # Find the specific tab to display
    current_tab = None
    current_tab_index = 0
    tab_links = []

    # Generate navigation links based on page category
    if category == "Election Tracker":
        # Show all Election Tracker pages as navigation
        for page_slug, page_data in tracker_pages.items():
            page_title = page_data["page_fields"].get("Democracy-page", "")
            tab_links.append({
                "title": page_title,
                "url": f"/{page_slug}",
                "is_active": page_slug == slug
            })
    elif category == "Democracy Data":
        # Show all Democracy Data pages as navigation
        for page_slug, page_data in data_pages.items():
            page_title = page_data["page_fields"].get("Democracy-page", "")
            tab_links.append({
                "title": page_title,
                "url": f"/{page_slug}",
                "is_active": page_slug == slug
            })
    else:
        # For other pages (like country pages), show tabs within the same page
        for i, tab in enumerate(sorted_tabs):
            tab_title = tab["tab_fields"].get("TabTitle") or tab["tab_fields"].get("Democracy-tab")
            tab_url_slug = tab_title.lower().replace(" ", "-").replace("&", "").replace("  ", "-")

            if len(sorted_tabs) > 1:
                hyphenated_url = f"{slug}-{tab_url_slug}"
                url = f"/{hyphenated_url}"
            else:
                url = f"/{slug}"

            tab_links.append({
                "title": tab_title,
                "url": url,
                "is_active": tab_slug == tab_url_slug or (tab_slug is None and i == 0)
            })

    # Find current tab
    for i, tab in enumerate(sorted_tabs):
        tab_title = tab["tab_fields"].get("TabTitle") or tab["tab_fields"].get("Democracy-tab")
        tab_url_slug = tab_title.lower().replace(" ", "-").replace("&", "").replace("  ", "-")

        if tab_slug == tab_url_slug or (tab_slug is None and i == 0):
            current_tab = tab
            current_tab_index = i

    if not current_tab:
        return HTMLResponse("Tab not found", status_code=404)

    # Build structured tab data
    tab_title = current_tab["tab_fields"].get("TabTitle") or current_tab["tab_fields"].get("Democracy-tab")
    tab_text = current_tab["tab_fields"].get("TabText", "")
    more_info = current_tab["tab_fields"].get("More info about this page", "")

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
                f"leadership within African governance and democracy.")

    # Sort subtabs by SubtabOrder
    sorted_subtabs = sorted(current_tab["subtabs"],
                            key=lambda subtab: int(subtab["subtab_fields"].get("SubtabOrder", "0")))

    subtabs = []
    for subtab in sorted_subtabs:
        subtab_title = subtab["subtab_fields"].get("SubtabTitle")
        subtab_text = subtab["subtab_fields"].get("SubtabText")

        years, sections_by_year = organize_sections_by_year(subtab)
        subtabs.append({
            "title": subtab_title,
            "text": subtab_text,
            "years": years,
            "sections_by_year": sections_by_year,
            "democracy_description": subtab["subtab_fields"].get("Description")
        })

    current_tab_data = {
        "title": tab_title,
        "text": tab_text,
        "more_info": more_info,
        "subtabs": subtabs
    }

    return templates.TemplateResponse(
        "tab_page.html", {
            "request": request,
            "page_title": page_title,
            "country_description": source["page_fields"].get("Text"),
            "current_tab": current_tab_data,
            "tab_links": tab_links,
            "category": category,
            "current_slug": slug,
            "current_tab_slug": tab_slug,
            "selected_year": year,
            "sidebar": {
                "tracker": tracker_pages,
                "democracy": data_pages,
                "countries": sorted_countries,
                "directory": directory_pages
            },
            "year": datetime.now().year,
            "version": datetime.now().timestamp(),
            "is_country_page": is_country_page
        })