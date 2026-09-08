"""Seed script with Indian ecommerce topic suggestions."""

from app.database import SessionLocal, engine, Base
from app.models import TopicSuggestion

SEED_TOPICS = [
    ("Complete Guide to Amazon FBA India in 2026: Fees, GST & Profit Margins", "Amazon FBA India", "amazon fba india, fba fees india, gst on amazon", 9),
    ("How to Register as Flipkart Seller: Step-by-Step Onboarding Guide 2026", "Flipkart Selling", "flipkart seller registration, flipkart seller hub", 9),
    ("GST for Ecommerce Sellers in India: TCS, TDS & Filing Guide", "GST & Compliance", "gst ecommerce india, tcs on ecommerce, gst filing sellers", 10),
    ("Meesho Supplier Program: How to Start Selling Without Investment", "Social Commerce", "meesho supplier, meesho selling, social commerce india", 8),
    ("Diwali Sale 2026: Amazon & Flipkart Seller Preparation Checklist", "Festive Season Selling", "diwali sale amazon, festive season selling india", 9),
    ("D2C Brand Building in India: From Shopify Store to ₹1 Crore Revenue", "D2C & Brand Building", "d2c india, shopify india, direct to consumer", 8),
    ("ONDC for Sellers: How Open Network for Digital Commerce Changes Indian Ecommerce", "Marketplace Trends", "ondc sellers, ondc india, open network commerce", 7),
    ("Instagram & WhatsApp Selling in India: Social Commerce Guide 2026", "Social Commerce", "instagram selling india, whatsapp business selling", 8),
    ("Shiprocket vs Delhivery vs BlueDart: Best Logistics Partner for Indian Sellers", "Logistics & Fulfillment", "shiprocket, delhivery, ecommerce logistics india", 7),
    ("Amazon PPC India: Complete Advertising Guide for Indian Marketplace Sellers", "Digital Marketing", "amazon ppc india, amazon advertising, sponsored products", 8),
    ("How to Reduce COD Returns on Flipkart & Amazon India", "Business Tips", "cod returns india, reduce rto ecommerce", 7),
    ("UPI & Digital Payments for Indian Ecommerce: Razorpay vs Paytm vs PhonePe", "Business Tips", "payment gateway india, razorpay ecommerce, upi payments", 6),
    ("Quick Commerce in India: Should Sellers List on Blinkit, Zepto & Instamart?", "Marketplace Trends", "quick commerce india, blinkit seller, zepto", 7),
    ("Export from India via Amazon Global Selling: Complete 2026 Guide", "Amazon FBA India", "amazon global selling india, export ecommerce", 8),
    ("Influencer Marketing for Indian D2C Brands: ROI & Strategy Guide", "Digital Marketing", "influencer marketing india, d2c marketing", 7),
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(TopicSuggestion).count()
        if existing > 0:
            print(f"Already have {existing} topics, skipping seed.")
            return
        for title, category, keywords, priority in SEED_TOPICS:
            db.add(TopicSuggestion(title=title, category=category, keywords=keywords, priority=priority))
        db.commit()
        print(f"Seeded {len(SEED_TOPICS)} topic suggestions.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
