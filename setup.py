from setuptools import setup, find_packages

import doberman

setup(
    name="doberman",
    version=doberman.__version__,
    description="Statistical Analysis of OIL",
    author="Ryan Harper, Darren Hoyland",
    author_email="<ryan.harper@canonical.com>, <darren.hoyland@canonical.com>",
    url="http://launchpad.net/~oil-ci",
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Programming Language :: Python",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Intended Audience :: Developers"],
    entry_points={
        "console_scripts": [
            'stats = doberman.stats.stats:main',
            'oil-cookie = doberman.oil_cookie:main',
            'crude-analysis = doberman.analysis.analysis:main',
            'refinery = doberman.refinery.refinery:main',
            'filing-station = doberman.filing_station.filing_station:main',
            'updatabase = doberman.upload_bugs_from_mock_to_db:main',
        ]
        },
    )
