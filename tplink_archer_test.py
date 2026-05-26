
from pathlib import Path

from updater.domain.models import Target
from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository
from updater.presentation.discord_bot.config import load_config

config = load_config(Path(".env"))
db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
target_repo = MongoTargetRepository(db.db)

target = target_repo.upsert(Target(
      name="TP-Link Archer BE400 V1.20",
      vendor="TP-Link",
      vendor_alias="archer-be400/v1.20",
      category="router",
  ))

targets = target_repo.list_all()

for index, item in enumerate(targets, start=1):
      print(f"{index}. {item.name} | vendor={item.vendor} | alias={item.vendor_alias} | mongo_id={item.id}")