import argparse
import sys

from core.html_report import generate_html_report
from core.publish_report import publish_report
from core.metrics_store import delete_metrics, filter_metrics, format_metric_row, list_metrics


def _parse_ids(value: str) -> list[int]:
    ids = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise argparse.ArgumentTypeError(f"Некорректный номер записи: {part}")
        ids.append(int(part))
    if not ids:
        raise argparse.ArgumentTypeError("Список номеров пуст")
    return ids


def _print_records(df) -> None:
    if df.empty:
        print("Записей нет.")
        return

    print(f"Всего записей: {len(df)}\n")
    for _, row in df.iterrows():
        print(format_metric_row(row))


def _confirm(rows, assume_yes: bool) -> bool:
    print("Будут удалены записи:")
    for row in rows:
        print(f"  - {format_metric_row(row)}")

    if assume_yes:
        return True

    answer = input("\nУдалить? [y/N]: ").strip().lower()
    return answer in ("y", "yes", "д", "да")


def _interactive_delete(assume_yes: bool, rebuild_report: bool) -> int:
    df = list_metrics()
    _print_records(df)
    if df.empty:
        return 0

    print("\nВведите номера для удаления через запятую (например: 1,3,5)")
    print("Или фильтр: geo=Uzbekistan page=HOME before=2026-07-01 errors")
    print("Пустой ввод — выход.")
    user_input = input("> ").strip()
    if not user_input:
        print("Отменено.")
        return 0

    display_ids = None
    geo = None
    page = None
    before = None
    after = None
    errors_only = False

    if user_input.replace(",", "").isdigit() or "," in user_input:
        display_ids = _parse_ids(user_input)
    else:
        for token in user_input.split():
            key, _, value = token.partition("=")
            key = key.lower()
            if key == "geo":
                geo = value
            elif key == "page":
                page = value
            elif key == "before":
                before = value
            elif key == "after":
                after = value
            elif key == "errors":
                errors_only = True

    return _run_delete(
        display_ids=display_ids,
        geo=geo,
        page=page,
        before=before,
        after=after,
        errors_only=errors_only,
        assume_yes=assume_yes,
        rebuild_report=rebuild_report,
    )


def _run_delete(
    *,
    display_ids=None,
    geo=None,
    page=None,
    before=None,
    after=None,
    errors_only=False,
    assume_yes=False,
    rebuild_report=True,
) -> int:
    df = list_metrics()
    if display_ids:
        preview = df[df["row_id"].isin(display_ids)]
    else:
        preview = filter_metrics(
            df,
            geo=geo,
            page=page,
            before=before,
            after=after,
            errors_only=errors_only,
        )

    if preview.empty:
        print("Подходящих записей для удаления не найдено.")
        return 0

    if not _confirm([row for _, row in preview.iterrows()], assume_yes):
        print("Отменено.")
        return 0

    deleted = delete_metrics(
        display_ids=display_ids,
        geo=geo,
        page=page,
        before=before,
        after=after,
        errors_only=errors_only,
    )
    print(f"Удалено записей: {len(deleted)}")

    if rebuild_report:
        generate_html_report()
        publish_report()

    return len(deleted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Удаление выбранных записей из reports/metrics.csv"
    )
    parser.add_argument("--list", action="store_true", help="Показать все записи с номерами")
    parser.add_argument("--ids", type=_parse_ids, help="Номера записей через запятую, как в отчёте")
    parser.add_argument("--geo", help="Удалить записи с указанным гео")
    parser.add_argument("--page", help="Удалить записи с указанной страницей (HOME)")
    parser.add_argument("--before", help="Удалить записи старше даты (YYYY-MM-DD)")
    parser.add_argument("--after", help="Удалить записи новее даты (YYYY-MM-DD)")
    parser.add_argument("--errors-only", action="store_true", help="Удалить только записи с ошибками")
    parser.add_argument("--yes", action="store_true", help="Не спрашивать подтверждение")
    parser.add_argument("--no-report", action="store_true", help="Не пересобирать HTML-отчёт")
    args = parser.parse_args(argv)

    if args.list:
        _print_records(list_metrics())
        return 0

    has_delete_args = any([
        args.ids,
        args.geo,
        args.page,
        args.before,
        args.after,
        args.errors_only,
    ])

    if not has_delete_args:
        return _interactive_delete(args.yes, not args.no_report)

    return _run_delete(
        display_ids=args.ids,
        geo=args.geo,
        page=args.page,
        before=args.before,
        after=args.after,
        errors_only=args.errors_only,
        assume_yes=args.yes,
        rebuild_report=not args.no_report,
    )


if __name__ == "__main__":
    sys.exit(main())