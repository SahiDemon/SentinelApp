from opensearch_logger import OpenSearchLogger

def main():
    print("Initializing OpenSearch Logger to check/create index...")
    # Initialize with default settings (host, auth, index name)
    logger = OpenSearchLogger()

    if logger.client: # Proceed only if the client initialized successfully
        print(f"Checking/Creating index '{logger.index_name}'...")
        logger.create_index_if_not_exists()
        print("Index setup process complete.")
    else:
        print("Skipping index creation as OpenSearch client failed to initialize.")
        print("Please check connection settings, credentials, and OpenSearch cluster status.")

if __name__ == "__main__":
    main() 