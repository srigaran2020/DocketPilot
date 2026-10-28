-- Runs once, when the Postgres volume is first created. A separate database for automated tests.
CREATE DATABASE docketpilot_test OWNER docketpilot;
