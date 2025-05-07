from setuptools import setup, find_packages

setup(
    name="escalate",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "slack_sdk",
        "pdpyras",  # PagerDuty Python REST API
        "jira",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "escalate=escalate.cli:main",
        ],
    },
)