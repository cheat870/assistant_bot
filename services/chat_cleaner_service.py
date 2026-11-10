import asyncio
import logging
from typing import Optional, List, Set, Any

logger = logging.getLogger(__name__)

def format_clean_notice_text() -> str:
    """Format clean completion announcement banner."""
    return (
        "🧹 *បានសម្អាតសារទាំងអស់ (ទាំងចាស់ និងថ្មី) ដោយជោគជ័យ!* ✨\n\n"
        "ប្រវត្តិសារទាំងអស់ត្រូវបានជម្រះស្អាតស្រឡះ ១០០% គ្មានសារចាស់ ឬសារថ្មីកកកុញទៀតឡើយ។\n"
        "សូមជ្រើសរើសមុខងារដែលចង់ប្រើប្រាស់បន្តខាងក្រោម៖"
    )

async def purge_chat_history(
    bot: Any,
    chat_id: int,
    current_msg_id: Optional[int] = None,
    sweep_depth: Optional[int] = None,
    extra_ids: Optional[List[int]] = None,
    max_cap: int = 1000
) -> int:
    """
    Purge all messages in the chat (both old and new):
    1. Collects tracked IDs from auto_clean_messages database table.
    2. Collects any tracked menu / alert IDs passed via extra_ids.
    3. Sweeps backwards from current_msg_id + 5 all the way to message 1 (capped at max_cap).
    4. Deletes in 100-item chunks via delete_messages with concurrent 20-item fallback via delete_message.
    5. Clears message tracking in database for this chat.
    Returns total deleted message count.
    """
    mids_to_delete: Set[int] = set()

    # 1. Add extra explicit IDs
    if extra_ids:
        for mid in extra_ids:
            if mid and isinstance(mid, int) and mid > 0:
                mids_to_delete.add(mid)

    # 2. Add tracked messages from local SQLite database
    try:
        from database import get_auto_clean_messages_for_chat
        db_records = get_auto_clean_messages_for_chat(chat_id)
        for _, rec_mid in db_records:
            if rec_mid and rec_mid > 0:
                mids_to_delete.add(rec_mid)
    except Exception as e_db:
        logger.debug(f"Could not load tracked auto_clean messages for chat {chat_id}: {e_db}")

    # 3. Add sweep range (both old messages all the way back, and recent/new messages)
    if current_msg_id and current_msg_id > 0:
        if sweep_depth is None or sweep_depth <= 0:
            # By default sweep all messages from 1 to current_msg_id (capped at max_cap)
            sweep_depth = min(current_msg_id, max_cap)
        else:
            sweep_depth = min(sweep_depth, max_cap)

        start_id = max(1, current_msg_id - sweep_depth)
        end_id = current_msg_id + 5
        mids_to_delete.update(range(start_id, end_id))

    if not mids_to_delete:
        return 0

    # Sort descending: delete newest messages first, working down to oldest
    sorted_mids = sorted(mids_to_delete, reverse=True)
    deleted_count = 0

    # 4. Batch delete in chunks of 100
    for i in range(0, len(sorted_mids), 100):
        chunk = sorted_mids[i:i + 100]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=chunk)
            deleted_count += len(chunk)
        except Exception:
            # Fallback to concurrent mini-chunks of 20 with asyncio.gather
            for j in range(0, len(chunk), 20):
                sub_chunk = chunk[j:j + 20]
                tasks = [bot.delete_message(chat_id=chat_id, message_id=mid) for mid in sub_chunk]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if res is True:
                        deleted_count += 1
                await asyncio.sleep(0.04)  # Anti-flood delay

    # 5. Clear tracking records from database
    try:
        from database import clear_auto_clean_messages_for_chat
        clear_auto_clean_messages_for_chat(chat_id)
    except Exception as e_clear:
        logger.debug(f"Could not clear auto_clean tracking for chat {chat_id}: {e_clear}")

    logger.info(f"Purged {deleted_count} messages for chat {chat_id} (both old and new).")
    return deleted_count
