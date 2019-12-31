import datetime
from mongoengine import *


class Review(DynamicDocument):
    """
    Data of a glassdoor review of a company, the glassdor company id and review id
    are required, the compound uniqueness is enforced in the index.
    """
    employer_name = StringField(required=True, max_length=50)
    employer_glassdoor_id = StringField(required=True, max_length=50)
    review_glassdoor_id = StringField(required=True, max_length=50)
    title = StringField(required=False, max_length=100)
    # job of the person reviewing
    job_title = StringField(required=False, max_length=300)

    # the actual text of the review
    pros = StringField(required=False)
    cons = StringField(required=False)
    advice_to_management = StringField(required=False)
    review_language = StringField(required=False, max_length=3)

    # review scores
    work_life_balance = FloatField(required=False)
    culture_and_values = FloatField(required=False)
    career_opportunities = FloatField(required=False)
    senior_management = FloatField(required=False)
    compensation_and_benefits = FloatField(required=False)
    overall_rating = FloatField(required=False)

    # sentiment score
    sentiment_score = FloatField(required=False)

    # recommendation tags (recommends, business outlook, ceo)
    recommendation_tags = ListField(StringField(required=False, max_length=30), required=False)
    date_last_modify = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "indexes": [
            #  #name stands for an hash index, $name stands for a text index, name stands for a normal btree index
            "#employer_glassdoor_id",
            "#employer_name",
            "overall_rating",

            {"fields": ["employer_glassdoor_id", "review_glassdoor_id"],
             "unique": True
             },

            # text index on name, hqs, industry
            {'fields': ["$job_title", "$title"],
             'default_language': 'english',
             'weights': {"job_title": 2, "title": 1}
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
        if self.compensation_and_benefits and not (0 <= self.compensation_and_benefits <= 5):
            raise ValidationError
        if self.overall_rating and not (0 <= self.overall_rating <= 5):
            raise ValidationError
        if self.sentiment_score and not (0 <= self.sentiment_score <= 5):
            raise ValidationError
