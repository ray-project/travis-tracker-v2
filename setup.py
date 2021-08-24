import setuptools

setuptools.setup(
    name="ray_ci_tracker",
    version="0.0.1",
    author="simon-mo",
    description="Ray CI Health Tracker",
    url="https://github.com/ray-project/travis-tracker-v2",
    packages=["ray_ci_tracker"],
    python_requires=">=3.7",
    install_requires=open("./requirements.txt").read().splitlines(),
    entry_points={"console_scripts": ["ray-ci=ray_ci_tracker.scripts:cli"]},
)