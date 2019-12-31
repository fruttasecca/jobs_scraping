import datetime
from mongoengine import *


class Company(DynamicDocument):
    """
    Data of a company, the only required field if the name.
    """
    name = StringField(required=True, max_length=50)
    glassdoor_id = StringField(required=False, max_length=50)

    # company general info
    website = StringField(required=False)
    headquarters = StringField(required=False)
    size = StringField(required=False)
    founded = StringField(required=False)
    industry = StringField(required=False)
    revenue = StringField(required=False)
    competitors = ListField(StringField(required=False))

    # aggregate glassdoor reviews info
    overall_rating = FloatField(required=False)
    culture_and_values = FloatField(required=False)
    career_opportunities = FloatField(required=False)
    work_life_balance = FloatField(required=False)
    senior_management = FloatField(required=False)
    ceo_rating = FloatField(required=False)
    biz_outlook = FloatField(required=False)
    recommend = FloatField(required=False)
    comp_and_benefits = FloatField(required=False)

    date_last_modify = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "indexes": [
            #  #name stands for an hash index, $name stands for a text index, name stands for a normal btree index
            "#glassdoor_id",
            "#name",


            # indexes on aggregate reviews scores
            "overall_rating",
            "ceo_rating",
            "biz_outlook",
            "recommend",
            "culture_and_value",
            "career_opportunities",
            "work_life_balance",
            "senior_management",

            # text index on name, hqs, industry
            {'fields': ["$name", "$headquarters", "$industry"],
             'default_language': 'english',
             'weights': {"name": 10, "headquarters": 5, "industry": 2}
             }
        ]
    }

    def clean(self):
        if self.work_life_balance and not (0 <= self.work_life_balance <= 5):
            raise ValidationError
        if self.culture_and_values and not (0 <= self.culture_and_values <= 5):
            raise ValidationError
        if self.career_opportunities and not (0 <= self.career_opportunities <= 5):
            raise ValidationError
        if self.senior_management and not (0 <= self.senior_management <= 5):
            raise ValidationError
        if self.overall_rating and not (0 <= self.overall_rating <= 5):
            raise ValidationError
        if self.ceo_rating and not (0. <= self.ceo_rating <= 100.):
            raise ValidationError
        if self.biz_outlook and not (0. <= self.biz_outlook <= 100.):
            raise ValidationError
        if self.recommend and not (0. <= self.recommend <= 100.):
            raise ValidationError
