import os
import asyncio


async def split_file(
    input_file: str,
    chunk_size: int = 2_000_000_000,
):
    """
    Splits a large file into smaller parts.

    The file is processed in small blocks so the entire
    file does not need to be loaded into RAM at once.
    """

    file_size = os.path.getsize(input_file)

    if file_size <= chunk_size:
        return [input_file]

    parts = []

    base_name = os.path.basename(input_file)
    output_dir = os.path.dirname(input_file)

    part_number = 1

    with open(input_file, "rb") as source:

        while True:
            part_name = (
                f"{base_name}.part"
                f"{part_number:03d}"
            )

            part_path = os.path.join(
                output_dir,
                part_name,
            )

            remaining = chunk_size

            with open(part_path, "wb") as part_file:

                while remaining > 0:
                    block = source.read(
                        min(64 * 1024, remaining)
                    )

                    if not block:
                        break

                    part_file.write(block)
                    remaining -= len(block)

            if os.path.getsize(part_path) == 0:
                os.remove(part_path)
                break

            parts.append(part_path)
            part_number += 1

            await asyncio.sleep(0)

    return parts
