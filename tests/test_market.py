from unittest import TestCase, mock

from app import market
from app.config import ScraperConfig

SUPERMARKET_HOME = """
<html><head><title>Fresh food and groceries | Big Chain Supermarket</title>
<meta name="description" content="Weekly offers on groceries across the UK."></head>
<body><h1>Supermarket offers</h1><p>Shop fruit, bread and milk.</p></body></html>
"""
PERSIAN_HOME = """
<html><head><title>Sahar | Persian supermarket in London</title></head>
<body><p>Saffron, barberries and fresh sangak bread from Iran.</p></body></html>
"""


class MarketTests(TestCase):
    def setUp(self):
        patcher = mock.patch.dict(market._synonyms, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_words_lose_endings_that_do_not_change_their_meaning(self):
        cases = {
            "iranian": "iran",
            "italian": "ital",
            "turkish": "turk",
            "japanese": "japan",
            "supermarkets": "supermarket",
            "dentists": "dentist",
            "cafes": "cafe",
            "pubs": "pub",
            "plumbers": "plumber",
            "glass": "glass",
        }
        self.assertEqual({word: market.stem(word) for word in cases}, cases)

    def test_listing_words_are_not_part_of_the_market(self):
        self.assertEqual(market.market_words("Independent Iranian shops in"), ["iranian"])

    def test_model_synonyms_are_kept_per_market_and_cleaned(self):
        config = ScraperConfig(niche="Iranian supermarket", location="London")
        answer = {"iranian": ["Persian", "Farsi", "https://bad.example", "x"], "supermarket": "grocer"}

        with mock.patch("app.market._ask_model", return_value=answer) as ask:
            market.prepare(config)
            market.prepare(config)

        ask.assert_called_once()
        self.assertEqual(
            market.concepts("Iranian supermarket"),
            [("iranian", "iran$", "persian", "pers$", "farsi"), ("supermarket",)],
        )

    def test_no_model_call_when_ai_is_off(self):
        config = ScraperConfig(niche="Iranian supermarket", location="London", ai_extraction="off")

        with mock.patch("app.market._ask_model") as ask:
            market.prepare(config)

        ask.assert_not_called()

    def _config(self, niche="Iranian supermarket"):
        return ScraperConfig(niche=niche, location="London")

    def test_a_chain_supermarket_is_off_an_iranian_supermarket_market(self):
        lead = market.judge({}, SUPERMARKET_HOME, self._config())

        self.assertEqual(
            lead, {"market_fit": "off_market", "market_fit_reason": "The site never mentions iranian."}
        )

    def test_a_shop_that_names_the_market_is_a_match(self):
        self.assertEqual(market.judge({}, PERSIAN_HOME, self._config())["market_fit"], "match")

    def test_a_synonym_from_the_model_counts_as_the_word(self):
        page = "<title>Sahar | Persian grocery and supermarket</title>"
        before = market.judge({}, page, self._config())["market_fit"]
        market._synonyms["iranian supermarket"] = {"iranian": ["persian"]}
        after = market.judge({}, page, self._config())["market_fit"]

        self.assertEqual((before, after), ("off_market", "match"))

    def test_a_different_name_for_the_kind_of_business_is_kept_but_unclear(self):
        page = "<title>Iranmehr | Iranian food shop</title><p>Rice, saffron and tea.</p>"

        lead = market.judge({}, page, self._config())

        self.assertEqual(lead["market_fit"], "unclear")
        self.assertIn("supermarket", lead["market_fit_reason"])

    def test_a_one_word_market_is_never_set_aside_by_the_word_check_alone(self):
        lead = market.judge({}, "<title>Bright Smile dental clinic</title>", self._config("dentists"))

        self.assertEqual(lead["market_fit"], "unclear")
