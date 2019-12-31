import re
import ast
from scrapy.spiders import Spider
from scrapy.http import Request, FormRequest

from items import country_to_id


class GlassdoorCompanies(Spider):
    name = 'glassdoor_companies'
    allowed_domains = ['glassdoor.com', "glassdoor.co.uk"]
    country = ""
    company = ""

    base_url_COM = "http://www.glassdoor.com"

    # used to get stuff from a queried dictionary
    info_types = ["Headquarters", "Size", "Founded", "Type", "Industry", "Revenue", "Competitors"]

    # used to find javascript variables in the page
    employer_RE = re.compile("'employer':\{.*?\}")

    def start_requests(self):
        """
        Start the first request from any page that is in reviews, so that we get the form in which to
        input data.
        :return:
        """
        url = "https://www.glassdoor.co.uk/Reviews/england-reviews-SRCH_IL.0,7_IS7287.htm"
        req = FormRequest(url=url, callback=self.query_form)
        yield req

    def query_form(self, response):
        """
        Query the input form with a location and a company keyword.

        :param response:
        :return:
        """

        yield FormRequest.from_response(
            response,
            formxpath="(//form)[1]",
            formdata={
                'sc.keyword': self.company.lower(),
                'locKeyword': '',
                'locT': "N",
                'locId': country_to_id.get(self.country.lower(), None)
            },
            callback=self.parse_companies_page,
            clickdata={
                "id": "HeroSearchButton",
                "class": "gd-btn-mkt"
            },
            # otherwise scrapy won't query the page because it has already called it in the previous request
            dont_filter=True
        )

    def parse_companies_page(self, response):
        """
        Parse the page containing a list of companies, for each company
        get to its page and get to all the next pages containing companies.

        :param response:
        :return:
        """

        # companies link
        path = "//div[@class = \"empInfo tbl \"]/div[1]/a[1]/@href"
        companies = response.xpath(path).getall()
        if companies:
            for company in companies:
                yield response.follow(company, callback=self.parse_company)

        # just get al links (previous page, current, etc and follow on all of them, scrapy
        # won't crawl stuff we have already visited anyway, this is useful because i've found
        # that sometimes glassdoor might swap around names etc., this was just less error prone
        next_pages = response.xpath("//div[@class= \"pagingControls cell middle\"]//@href").getall()
        if next_pages:
            for next_page in next_pages:
                yield response.follow(next_page, self.parse_companies_page)

    def parse_company(self, response):
        """
        Parse the page of a company, getting it's general info and then
        following to the reviews page of said company.

        :param response:
        :return:
        """

        # get script code that contains some useful variables
        script_variables = response.xpath('//script/text()').getall()
        if script_variables is not None:
            script_variables = "".join((" ".join(script_variables)).split())
            script_variables = script_variables.replace("\"", "'")

            employer = self.employer_RE.findall(script_variables)
            if employer is not None:
                employer = employer[0]
                employer = employer[11:]
                try:
                    employer = ast.literal_eval(employer)
                except:
                    pass
        else:
            employer = dict()

        res = dict()
        res["website"] = response.xpath("//span[@class = \"value website\"]/a/@href").get()

        # see the info_types field to see what we are getting
        info_query = "//div[@class = \"infoEntity\" and label/text() = \"%s\"]/span/text()"
        for info_name in self.info_types:
            res[info_name.lower()] = response.xpath(info_query % info_name).get()

        res["employer_name"] = response.xpath(
            "//div[@class = \"header cell info\"]/h1[@class = \" strong tightAll\"]/@data-company").get()
        res["employer_glassdoor_id"] = employer.get("id", None)
        res["type"] = "company_general_info"
        yield res

        if res["employer_name"] and res["employer_glassdoor_id"]:
            # get aggregate reviews info
            yield Request("https://www.glassdoor.co.uk/api/employer/%s-rating.htm" % res["employer_glassdoor_id"],
                          self.parse_aggregate_info(res["employer_name"], res["employer_glassdoor_id"]))

        # after getting info about the company go to parse its reviews
        reviews_page = "//a[@class = \"eiCell cell reviews \"]/@href"
        reviews_page = response.xpath(reviews_page).get()
        if reviews_page and res["employer_name"] and res["employer_glassdoor_id"]:
            # base_url_UK does not seem to be working
            yield Request(self.base_url_COM + reviews_page,
                          self.parse_reviews_page(res["employer_name"], res["employer_glassdoor_id"]))

    def parse_reviews_page(self, employer_name, employer_id):
        """
        Parse the reviews of a company, the actual function doing that
        is wrapped with a defined employer_name and employer_id so that it can output
        items with these fields so that they can be later matched with the relative company-
        :param employer_name:
        :param employer_id:
        :return:
        """

        def parse_reviews_page_wrapped(response):

            # for each review get its content
            page_reviews = response.xpath("//ol/li[contains(@id, \"empReview\")]")
            if page_reviews:
                for review in page_reviews:
                    res = dict()
                    res["employer_name"] = employer_name
                    res["employer_glassdoor_id"] = employer_id
                    res["review_glassdoor_id"] = review.xpath("./@id").get()

                    res["title"] = review.xpath(".//h2/a[@class = \"reviewLink\"]/span/text()").get()
                    res["job_title"] = review.xpath(".//span[@class = \"authorJobTitle middle reviewer\"]/text()").get()

                    res["work_life_balance"] = review.xpath(
                        ".//div[text()='Work/Life Balance']/following-sibling::node()/@title").get()
                    res["culture"] = review.xpath(
                        './/div[text() = "Culture & Values"]/following-sibling::node()/@title').get()
                    res["career_opportunities"] = review.xpath(
                        ".//div[text() = \"Career Opportunities\"]/following-sibling::node()/@title").get()
                    res["senior_management"] = review.xpath(
                        ".//div[text() = \"Senior Management\"]/following-sibling::node()/@title").get()
                    res["compensation_and_benefits"] = review.xpath(
                        ".//div[text() = \"Compensation and Benefits\"]/following-sibling::node()/@title").get()
                    res["overall"] = review.xpath(".//span[@class = \"value-title\"]/@title").get()

                    # recommendation tags (recommends, outlook, ceo)
                    res["recommendation_tags"] = review.xpath(
                        ".//div[contains(@class, \"recommends\")]//text()").getall()

                    # gets pros, cons, advice for management by changing the element index ([%s])
                    reviewPath = "((.//div[@class = \"mt-md common__EiReviewTextStyles__allowLineBreaks\"][%s]//p)[" \
                                 "2])/text() "

                    res['pros'] = review.xpath(reviewPath % 1).get()
                    res['cons'] = review.xpath(reviewPath % 2).get()
                    res['advice_to_management'] = review.xpath(reviewPath % 3).get()
                    res["type"] = "review"
                    yield res

            # follow the next pages
            next_url = response.xpath("//li[@class='next']//@href").get()
            if next_url:
                response.follow(next_url, self.parse_reviews_page(employer_name, employer_id))

        return parse_reviews_page_wrapped

    def parse_aggregate_info(self, employer_name, employer_id):
        """
        Parse the information of aggregated reviews.

        """

        def parse_aggregate_info_wrapped(response):
            text = response.text
            try:
                text = re.sub("false", "False", text)
                text = re.sub("true", "True", text)
                text = ast.literal_eval(text)

                res = dict()
                res["employer_name"] = employer_name
                res["employer_glassdoor_id"] = employer_id
                for rating in text["ratings"]:
                    if rating["hasRating"]:
                        res[rating["type"]] = rating["value"]
                    else:
                        res[rating["type"]] = None
                res["type"] = "company_aggregate_reviews_info"
                yield res

            except:
                yield None

        return parse_aggregate_info_wrapped
