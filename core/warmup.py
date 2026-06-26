def warmup(page):

    page.goto(
        "https://fastpari.com",
        wait_until="load",
        timeout=60000
    )

    print("WARMUP DONE")

    