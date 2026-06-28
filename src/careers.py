def scrape_company_careers(company_name: str, careers_url: str) -> list[dict]:
    """Scrapes a company's careers page for jobs.

    Stub for Session 2: add one elif branch per company scraper.
    """
    try:
        if company_name is None:
            return []
        # elif company_name == "Careem":
        #     return _scrape_careem(careers_url)
        else:
            print(f"Careers scraper not yet implemented for {company_name} - add manually")
            return []
    except Exception as e:
        print(f"ERROR: scrape_company_careers failed for {company_name}: {e}")
        return []
