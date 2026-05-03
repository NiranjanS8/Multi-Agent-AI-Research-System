from app.pipeline import run_research_pipeline


if __name__ == "__main__":
    topic = input("\n Enter a research topic: ")
    run_research_pipeline(topic=topic)
