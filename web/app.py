from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def home():
    deals = [
        {
            "title": "Today's Best Deals",
            "description": "Hand-picked deals from Amazon US",
            "url": "#",
        },
        {
            "title": "Tech Deals",
            "description": "Laptops, accessories, gadgets and more",
            "url": "#",
        },
        {
            "title": "Gaming Deals",
            "description": "Gaming gear and accessories",
            "url": "#",
        },
        {
            "title": "Home Deals",
            "description": "Useful products for your home",
            "url": "#",
        },
    ]

    return render_template("index.html", deals=deals)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )
