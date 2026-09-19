import asyncio
from functools import partial
from pathlib import Path
from typing import List
from taskmonad import Task, TaskContext

# --- Шаги задачи ---

def download_file(url: str, dest_path: str) -> Task[str]:
    async def comp(ctx: TaskContext):
        await asyncio.sleep(0.2)  # Имитация Playwright/HTTP
        content = f"Данные из источника {url}\n"
        Path(dest_path).write_text(content, encoding="utf-8")
        return ctx, dest_path
    return Task(name=f"Download({dest_path})", computation=comp)

def read_all_files(file_paths: List[str]) -> Task[List[str]]:
    async def comp(ctx: TaskContext):
        contents = [Path(p).read_text(encoding="utf-8") for p in file_paths]
        return ctx, contents
    return Task(name="ReadAllFiles", computation=comp)

def merge_and_save(output_path: str, contents: List[str]) -> Task[str]:
    async def comp(ctx: TaskContext):
        merged = "\n".join(contents)
        Path(output_path).write_text(merged, encoding="utf-8")
        return ctx.set("report_path", output_path), output_path
    return Task(name="MergeAndSave", computation=comp)

def cleanup_files(files: List[str]) -> Task[None]:
    async def comp(ctx: TaskContext):
        for path in files:
            Path(path).unlink(missing_ok=True)
        return ctx, None
    return Task(name="CleanupFiles", computation=comp)

def dispatch_report(report_path: str) -> Task[str]:
    async def comp(ctx: TaskContext):
        await asyncio.sleep(0.1)
        tracking_id = f"REP-{abs(hash(report_path)) % 100000}"
        return ctx.set("tracking_id", tracking_id), tracking_id
    return Task(name="DispatchReport", computation=comp)

def notify_success(tracking_id: str, ctx: TaskContext):
    print(f"✅ [УВЕДОМЛЕНИЕ] Отчет успешно отправлен! Трек-номер: {tracking_id}")

def notify_error(err: Exception, ctx: TaskContext):
    print(f"🚨 [УВЕДОМЛЕНИЕ] Сбой в пайплайне: {err}")

# --- Сборка пайплайна ---

sources = [
    ("https://api.one.org/data", "tmp_1.txt"),
    ("https://api.two.org/data", "tmp_2.txt"),
    ("https://api.three.org/data", "tmp_3.txt"),
]
temp_files = [path for _, path in sources]
final_report = "hourly_aggregated_report.txt"

download_tasks = [download_file(url, path) for url, path in sources]
save_report = partial(merge_and_save, final_report)

pipeline = (
    Task("HourlyReportPipeline")
    .when(lambda do: do.hourly())
    .success(notify_success)
    .error(notify_error)
    >> Task.parallel(*download_tasks)
    >> read_all_files
    >> save_report
    << cleanup_files(temp_files)                  # <--- Оператор <<: очищает файлы, но оставляет report_path для dispatch_report
    >> dispatch_report
)

async def main():
    print("=== Запуск taskmonad demo ===")
    ctx, result = await pipeline.run()

    if not isinstance(result, Exception):
        print(f"\nСодержимое сформированного отчета ({final_report}):")
        print(Path(final_report).read_text(encoding="utf-8"))
        Path(final_report).unlink(missing_ok=True)

if __name__ == "__main__":
    asyncio.run(main())