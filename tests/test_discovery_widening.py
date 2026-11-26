import time
from unittest import TestCase, mock

from app import listings, market
from app.config import ScraperConfig
from app.local_data import _district_name, _same_business
from app.search import QUERY_BATCH, build_queries, search_business_sites

LIST_ARTICLE = """
<html><head><title>Best Persian supermarkets in London</title></head><body>
<nav><a href="https://other-persianguide.co.uk/">Other guides</a></nav>
<h1>Best Persian supermarkets in London</h1>
<h2>1. Sahar Supermarket - Kensington</h2>
<p>Fresh sangak daily. <a href="https://sahar-supermarket.co.uk/">Website</a></p>
<h2>2. Golestan Foods</h2><p>A family shop in Ealing.</p>
<h2>Opening hours</h2>
<h3>Supermarkets in Manchester</h3>
<a href="https://wa.me/447000">WhatsApp</a>
<a href="https://www.s-sols.com/">Optimized by Seraphinite</a>
<footer><a href="https://cookiebanner.co.uk/">Cookie settings</a></footer>
</body></html>
"""


class ListingTests(TestCase):
    def test_a_list_article_gives_business_links_and_names(self):
        found = listings.harvest("https://persianguide.co.uk/best-persian-supermarkets", html=LIST_ARTICLE)

        self.assertEqual([link["url"] for link in found["links"]], ["https://sahar-supermarket.co.uk/"])
        self.assertEqual(found["names"], ["Sahar Supermarket", "Golestan Foods"])

    def test_directory_pages_and_list_titles_are_listings_not_businesses(self):
        self.assertTrue(
            listings.looks_like_listing("https://persianguide.co.uk/a", "Top 10 Persian shops in London")
        )
        self.assertTrue(
            listings.looks_like_listing("https://cylex-uk.co.uk/company/mehar-supermarket-1", "Mehar")
        )
        # A shop often titles its own home page this way, so it is not taken for a list.
        self.assertFalse(
            listings.looks_like_listing("https://asamarket.com/", "ASA Market - Persian grocery in London")
        )
        self.assertFalse(
            listings.looks_like_listing("https://sahar.co.uk/", "Sahar Supermarket | Fresh bread")
        )
        self.assertFalse(listings.looks_like_listing("https://www.facebook.com/sahar", "Best shop"))

    def test_names_with_a_market_word_are_looked_up_first(self):
        ranked = listings.rank_names(["Golestan", "Bahar Supermarket", "Kish"], "Iranian supermarket")

        self.assertEqual(ranked[0], "Bahar Supermarket")


class LocalNameTests(TestCase):
    def test_a_namesake_with_only_common_words_is_not_the_same_business(self):
        wanted = ["aran supermarket", "ava supermarket", "zamzam supermarket", "milad supermarket"]

        self.assertTrue(_same_business("Zam Zam Supermarket", "zamzam supermarket", wanted))
        self.assertTrue(_same_business("Milad Supermarket", "milad supermarket", wanted))
        self.assertFalse(_same_business("Afran Supermarket", "aran supermarket", wanted))
        self.assertFalse(_same_business("Supermarket", "ava supermarket", wanted))

    def test_district_names_lose_their_administrative_prefix(self):
        self.assertEqual(_district_name("London Borough of Ealing"), "Ealing")
        self.assertEqual(_district_name("Royal Borough of Kensington and Chelsea"), "Kensington and Chelsea")
        self.assertEqual(_district_name("City of Westminster"), "Westminster")


class QueryPlanTests(TestCase):
    def setUp(self):
        patcher = mock.patch.dict(market._synonyms, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_queries_cover_synonyms_lists_and_every_district(self):
        market._synonyms["iranian supermarket"] = {"iranian": ["persian"]}

        queries = build_queries("Iranian supermarket", "London", ["Ealing", "Barnet"])

        self.assertIn("persian supermarket London", queries)
        self.assertIn("best Iranian supermarket in London", queries)
        self.assertIn("Iranian supermarket Ealing London", queries)
        self.assertIn("persian supermarket Barnet London", queries)

    def test_each_pass_runs_the_next_batch_of_queries(self):
        areas = [f"District {index}" for index in range(30)]
        asked: list[str] = []

        class Provider:
            name = "web"

            def areas(self, _location):
                return areas

            def search(self, query, _limit, _offset=0):
                asked.append(query)
                return []

        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)
        diagnostics = {}
        search_business_sites(config, provider=Provider(), diagnostics=diagnostics)
        first = list(asked)
        asked.clear()
        search_business_sites(config, provider=Provider(), start_page=diagnostics["next_search_page"])

        plan = build_queries("salons", "London", areas)
        self.assertEqual(first, plan[:QUERY_BATCH])
        self.assertEqual(asked, plan[QUERY_BATCH : QUERY_BATCH * 2])


class ListingSearchTests(TestCase):
    def setUp(self):
        patcher = mock.patch.dict(market._synonyms, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _provider(self, name_results=None):
        class Provider:
            name = "hybrid"

            def __init__(self):
                self.names_asked: list[list[str]] = []

            def search(self, query, _limit, _offset=0):
                if query.startswith('"'):
                    return (name_results or {}).get(query, [])
                return [
                    {
                        "url": "https://persianguide.co.uk/best-persian-supermarkets-london",
                        "title": "Best Persian supermarkets in London",
                        "snippet": "Our pick of Iranian shops in London",
                    }
                ]

            def find_names(self, names, _location):
                self.names_asked.append(list(names))
                if "Golestan Foods" in names:
                    return [
                        {
                            "source": "osm_local",
                            "sources": ["local"],
                            "domain": "osm-N-7",
                            "title": "Golestan Foods",
                            "url": "",
                            "phone": "020 7000 0007",
                        }
                    ]
                return []

        return Provider()

    def test_a_list_page_is_read_for_its_businesses_and_is_not_a_lead_itself(self):
        provider = self._provider()
        config = ScraperConfig(niche="Iranian supermarket", location="London", delay_seconds=0)
        diagnostics = {}

        with mock.patch("app.listings.fetch_page", return_value=LIST_ARTICLE):
            sites = search_business_sites(config, provider=provider, diagnostics=diagnostics)

        by_domain = {site["domain"]: site for site in sites}
        self.assertNotIn("persianguide.co.uk", by_domain)
        self.assertEqual(
            by_domain["sahar-supermarket.co.uk"]["source_evidence"][0]["url"],
            "https://persianguide.co.uk/best-persian-supermarkets-london",
        )
        self.assertEqual(by_domain["osm-N-7"]["phone"], "020 7000 0007")
        self.assertEqual(diagnostics["list_pages_read"], 1)
        self.assertEqual(diagnostics["listed_businesses"], 1)

    def test_names_left_over_are_looked_up_on_the_next_pass(self):
        found_site = {
            "url": "https://kish-market.co.uk/",
            "title": "Kish Market | Persian groceries",
            "snippet": "London",
        }
        provider = self._provider({'"Kish Market" London': [found_site]})
        config = ScraperConfig(niche="Iranian supermarket", location="London", delay_seconds=0)

        sites = search_business_sites(config, provider=provider, pending_names=["Kish Market"])

        self.assertIn("kish-market.co.uk", {site["domain"] for site in sites})

    def test_running_out_of_time_keeps_what_was_found(self):
        provider = self._provider()
        config = ScraperConfig(niche="Iranian supermarket", location="London", delay_seconds=0)

        sites = search_business_sites(config, provider=provider, deadline=time.monotonic() - 1)

        self.assertEqual(sites, [])


class ListingSignalTests(TestCase):
    def test_a_page_titled_by_the_market_in_a_city_is_a_listing(self):
        niche, location = "Iranian supermarket", "London UK"

        self.assertTrue(
            listings.looks_like_listing(
                "https://grocers.co.uk/", "Iranian Grocery Stores in London - Grocers", set(), niche, location
            )
        )
        self.assertTrue(
            listings.looks_like_listing(
                "https://magazine.co.uk/2024/08/23/shops/", "Shops", set(), niche, location
            )
        )
        self.assertTrue(
            listings.looks_like_listing(
                "https://persiandirectory.co.uk/en/london/iranian-supermarket/",
                "Persian shops",
                set(),
                niche,
                location,
            )
        )
        self.assertFalse(
            listings.looks_like_listing(
                "https://asamarket.com/", "ASA Market - Persian grocery in London", set(), niche, location
            )
        )

    def test_one_word_names_are_not_looked_up(self):
        self.assertEqual(
            listings.lookup_names(["Bakery", "Verisure", "Zamzam Supermarket"]), ["Zamzam Supermarket"]
        )
