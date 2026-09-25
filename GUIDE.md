# Warm Prospect Radar — scraper-first milestone

1. Acquire public business sources, prioritising About and company information.
2. Extract structured business, contact, social, GICS, product and technology data.
3. Preserve raw versioned snapshots locally and important structured records in Supabase.
4. Review explainable likelihood and prospect scores in the Flask interface.
5. Keep all outreach actions disabled until the scraping workflow is reviewed and approved. 

See README.md for installation, Supabase SQL order, Ollama/Together AI setup,
Wikipedia sample loading, Windows/WSL commands, tests, and security boundaries.

# FILES 
==> db/functions_v2.sql <==

==> db/sample_data_loader.py <==
# load sample data from S&P 500 companies into the database.
==> db/schema_v1.sql <==
-- make PostgreSQL database
-- Use Supabase

-- Star schema:
-- central table: Buisnesses
--     buisness-id (long integer, primary key)
--     buisness-name (text)
--     buisness-city (text)
--     buisness-country (text)
-- this part onwards is categorised as S&P 500's classification system, which is a standard for classifying buisnesses into sectors and industries
--     buisness-sector (text/enumerated) -- 11 types
--     buisness-industry-group (text/enumerated) -- 24 types
--     buisness-industry (text/enumerated) -- 69 types
--     buisness-sub-industry (text/enumerated) -- 158 types

-- table 2: Buisness social media
--    buisness-id
--    buisness-website (make array/tuple)
--    buisness-phone-number (make array/tuple)
--    buisness-whatsapp-number (make array/tuple)
--    buisness-landline-number (make array/tuple)
--    buisness-facebook (make array/tuple)
--    buisness-twitter (make array/tuple)
--    buisness-instagram (make array/tuple)
--    buisness-linkedin (make array/tuple)
--    buisness-youtube (make array/tuple)
--    buisness-github (make array/tuple)
--    buisness-discord (make array/tuple)

-- thinking about a different table for each social media plaform written here.
-- Like each with its own specifications so the json of a buisness will have a different section for each social media platform and the data will be stored in different tables for each social media platform. 
-- This will make it easier to query and manage the data.

-- table 3: Buisness Prospects
--    buisness-id
--    buisness-scale  (make enumerated data type: sort between 10 different options)
--    prospect-score  (0-100 score)
--    prospect-likelihood (percentage between 0-100)

-- table 4: buisness-expenditure
--   buisness-id
--   date-time (make a timestamp+date time according to GMT timezone)
--   amount-spent (3 digit decimal number, like 100.000)

-- table 5: buisness-sales
--   buisness-id
--   date-time (make a timestamp+date time according to GMT timezone)
--   amount-earned (3 digit decimal number, like 100.000)

-- table 6: buisness-outreach
--   buisness-id
--   date-time (make a timestamp+date time according to GMT timezone)
--   type (enumerated data type: email, social media post, comment, others(other can be defined by us))
--   data  -- this will contain the outreach data, like email, social media post, etc.

-- add cascading delete but instead of delete we will archive data so we need to make a archive database/archive star schema which will be a copy of all this but it is for archiving purposes and anything deleted from here willbe transfered to there.
==> src/frontend/__init__.py <==
# We will make frontend in this folder
# HTML, CSS, JS, Flask is recommended stack
# For starters let's make these pages:
# 1. Home page
# 2. buisnesses display like a database view with search and filter options
# 3. buisnesses details page with all the data and graphs and charts
# 4. buisnesses outreach page with all the data and graphs and charts
# 5. progress with buisnesses managemetn
# 6. a page where actions towards a diffferent buisness will be approved or rejected by the user and the user will be able to see the progress of the actions taken toward each buisness.
# 7. a chatbot for user help and support and also for user to ask questions about the data and get answers in a conversational way.
# other pages will be added...

==> src/outreach/comment.py <==

==> src/outreach/email.py <==

==> src/outreach/message.py <==

==> src/outreach/other.py <==

==> src/outreach/picture.py <==

==> src/outreach/posts.py <==

==> src/outreach/__init__.py <==
# this folder is for managing outreach to different buisnesses in different ways.
# some main ways which i thought of are named as files in the folder.
# Each file will have its own functions and classes to manage outreach in that way.

==> src/scraper/facebook.py <==

==> src/scraper/instagram.py <==

==> src/scraper/linkedin.py <==

==> src/scraper/scraper.py <==
# save a json of a buisness data into database/data bucket on supabase and locally as well.
# name of json=f"{buisness-id}-v{version}.json"

# load scraped data into a database

==> src/scraper/twitter.py <==

==> src/scraper/webpape.py <==
# take a website as argument and return json data of the website
from pathlib import Path



class WebScraper:
    def __init__(self, url):
        self.url = url

    def scrape(self):
        # Implement scraping logic here
        pass


    def return_json(self, path:Path):
        # fetch path from .env file 
        # Convert scraped data to JSON format
        pass
==> src/scraper/__init__.py <==
# this folder is for designing scrapers that will scrape entire webpages of different sites
# first we willscrape raw webpages. 
# Then pass to small LLM (locally or serverless-inference but we will decide abut that)
# LLM will return json in an exact format. We can use that json to extract data of fields and fill our database.
# That's all. 

# The scrapper will also act as headers which will can be used to query. 
# Like it's given a website/insta page/insta post/linkedin post/linkedin profile etc and it will return data. 
# Storage in database is an option. 
# Storage in json is compulsory for record keeping uk. 
# If a json already exists then it's updated(updates will only be such that they append. Not remove.) and used.
