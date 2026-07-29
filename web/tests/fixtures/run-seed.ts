import { seedAppDatabase } from "./seed-app-database";

seedAppDatabase()
  .then(({ publicationId }) => {
    console.log(`Seeded market_documents_app_test -- publication ${publicationId}`);
  })
  .catch((error) => {
    console.error("Seeding failed:", error);
    process.exitCode = 1;
  });
