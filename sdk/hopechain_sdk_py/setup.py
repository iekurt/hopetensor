from setuptools import setup, find_packages
setup(
  name="hopechain-sdk",
  version="0.1.0",
  description="HOPE Chain Decentralized AI SDK (Python)",
  packages=find_packages(),
  install_requires=["requests>=2.31.0"],
  python_requires=">=3.9",
)
