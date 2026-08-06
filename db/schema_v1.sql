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
