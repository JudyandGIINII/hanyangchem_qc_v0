-- Synthetic disposable-test principal only; production roles are never created by migrations.
CREATE ROLE hyc_app_test LOGIN PASSWORD 'TEST_FIXTURE_ONLY_P2_APP_PASSWORD';
GRANT CONNECT ON DATABASE hyc_p2_test TO hyc_app_test;
