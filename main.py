"""Worker - Main entry point."""

if __name__ == "__main__":
    from src.worker import main
    import asyncio
    
    asyncio.run(main())
