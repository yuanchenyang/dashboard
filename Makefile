APP = dashboard.py

run-debug:
	export FLASK_APP=${APP}; export FLASK_ENV=development; flask run

run-prod:
	export FLASK_APP=${APP}; export FLASK_ENV=production; flask run
