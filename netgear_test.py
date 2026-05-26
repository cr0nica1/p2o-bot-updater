
from pathlib import Path

from updater.domain.models import Target
from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository
from updater.presentation.discord_bot.config import load_config

config = load_config(Path(".env"))
db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
target_repo = MongoTargetRepository(db.db)

target = target_repo.upsert(Target(
      name="Netgear MR6150 - Nighthawk M6 Mobile Hotspot",
      vendor="Netgear",
      vendor_alias="mr6150",
      category="mobile_hotspot",
  ))

targets = target_repo.list_all()

for index, item in enumerate(targets, start=1):
      print(f"{index}. {item.name} | vendor={item.vendor} | alias={item.vendor_alias} | mongo_id={item.id}")