import re
import ast
from scrapy.spiders import Spider
from scrapy.http import FormRequest

from items import country_to_id


class GlassdoorJobs(Spider):
    name = 'glassdoor_jobs'
    # .it mostly for debugging
    allowed_domains = ['glassdoor.com', "glassdoor.co.uk", "glassdoor.it"]
    country = ""
    job = ""

    # used to find javascript variables in the page
    jobRE = re.compile("'job':\{.*?\}")
    employerRE = re.compile("'employer':\{.*?\}")

    def start_requests(self):
        """
        Start the first request from any page that is in jobs, so that we get the form in which to
        input data.
        :return:
        """
        url = "https://www.glassdoor.com/Job/chill-jobs-SRCH_KE0,5.htm"

        req = FormRequest(url=url,
                          callback=self.query_index)
        self.logger.info("Starting to crawl")
        yield req

    def query_index(self, response):
        """
        Query the input form with a location and a job keyword.

        :param response:
        :return:
        """

        yield FormRequest.from_response(
            response,
            formxpath="(//form)[1]",
            formdata={
                'sc.keyword': self.job,
                'locKeyword': '',
                'locT': "N",
                'locId': country_to_id.get(self.country.lower(), None)
            },
            callback=self.parse_jobs_page,
            clickdata={
                "id": "HeroSearchButton",
                "class": "gd-btn-mkt"
            },
            dont_filter=True
        )

    def parse_jobs_page(self, response):
        """
        Parse the page containing a list of jobs, for each job
        get to its page and get to all the next pages containing jobs.

        :param response:
        :return:
        """

        # job links
        path = "(//li[@class = \"jl\"]/div[1]/a[1]/@href)"
        jobs = response.xpath(path).getall()
        if jobs is not None:
            for job in jobs:
                yield response.follow(job, callback=self.parse_job)

        # just get al links (previous page, current, etc and follow on all of them, scrapy
        # won't crawl stuff we have already visited anyway, this is useful because i've found
        # that sometimes glassdoor might swap around names etc., this was just less error prone
        next_pages = response.xpath("//div[@class= \"pagingControls cell middle\"]//@href").getall()
        if next_pages is not None:
            for next_page in next_pages:
                yield response.follow(next_page, self.parse_jobs_page)

    def parse_job(self, response):
        """
        Parse the page of a job offer, getting it's info.

        :param response:
        :return:
        """
        title = response.xpath("//head/title/text()").get()

        description_text = "//div[@class = \"jobDescriptionContent desc\"]//text()"
        description_html = "//div[@class = \"jobDescriptionContent desc\"]"
        description_text = response.xpath(description_text).getall()
        description_html = response.xpath(description_html).get()

        # get script code that contains some useful variables
        script_variables = response.xpath('//script/text()').getall()
        if script_variables is not None:
            script_variables = "".join((" ".join(script_variables)).split())
            script_variables = script_variables.replace("\"", "'")

            job = self.jobRE.findall(script_variables)
            if job is not None:
                job = job[0]
                job = job[6:]
                try:
                    job = ast.literal_eval(job)
                except:
                    pass

            employer = self.employerRE.findall(script_variables)
            if employer is not None:
                employer = employer[0]
                employer = employer[11:]
                try:
                    employer = ast.literal_eval(employer)
                except:
                    pass
        else:
            job = dict()
            employer = dict()

        res = dict()
        res["title"] = title
        res["description_html"] = description_html
        res["description_text"] = description_text
        res["job_title"] = response.xpath("//div[@class = \"jobViewJobTitleWrap\"]/h2/text()").get()
        res["city"] = job.get("city", None)
        res["state"] = job.get("state", None)
        res["country"] = job.get("country", None)
        res["job_glassdoor_id"] = job.get("id", None)
        res["employer_name"] = response.xpath("//div[@class = \"summaryColumn\"]/div/span/text()").get()
        res["employer_glassdoor_id"] = employer.get("id", None)
        res["type"] = "job"
        yield res
