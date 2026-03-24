from flask import Flask, jsonify, request
import tweepy
import pandas as pd
from nltk.sentiment.vader import SentimentIntensityAnalyzer

import config # Import your config file

app = Flask(__name__)

# --- Twitter API Setup ---
try:
    auth = tweepy.OAuth1UserHandler(
        config.TWITTER_API_KEY,
        config.TWITTER_API_SECRET,
        config.TWITTER_ACCESS_TOKEN,
        config.TWITTER_ACCESS_SECRET
    )
    api = tweepy.API(auth, wait_on_rate_limit=True)
    api.verify_credentials() # Verify credentials
    print("Twitter API authentication successful")
except Exception as e:
    print(f"Error during Twitter API authentication: {e}")
    api = None

# --- Sentiment Analysis Setup ---
sia = SentimentIntensityAnalyzer()

def get_sentiment(text):
    scores = sia.polarity_scores(text)
    if scores['compound'] >= 0.05:
        return 'positive'
    elif scores['compound'] <= -0.05:
        return 'negative'
    else:
        return 'neutral'

# --- Data Fetching Function ---
def get_tweets(keywords, count=100):
    tweets_data = []
    if api is None:
        print("Twitter API not available. Using mock data.")
        # Mock data for development
        mock_tweets = [
            {
                'text': f"I love {keywords}! It's amazing!",
                'user': 'User1',
                'created_at': '2026-03-24T08:00:00',
                'retweets': 10,
                'likes': 20,
                'sentiment': 'positive'
            },
            {
                'text': f"I hate {keywords}. It's terrible.",
                'user': 'User2',
                'created_at': '2026-03-24T08:05:00',
                'retweets': 5,
                'likes': 2,
                'sentiment': 'negative'
            },
            {
                'text': f"The {keywords} is okay, nothing special.",
                'user': 'User3',
                'created_at': '2026-03-24T08:10:00',
                'retweets': 0,
                'likes': 5,
                'sentiment': 'neutral'
            },
            {
                'text': f"Just saw something about {keywords}. Interesting.",
                'user': 'User4',
                'created_at': '2026-03-24T08:15:00',
                'retweets': 3,
                'likes': 8,
                'sentiment': 'neutral'
            },
            {
                'text': f"{keywords} is the best thing ever!",
                'user': 'User5',
                'created_at': '2026-03-24T08:20:00',
                'retweets': 50,
                'likes': 100,
                'sentiment': 'positive'
            }
        ]
        # Limit to count
        return mock_tweets[:count]

    try:
        # Using search_tweets for backward compatibility, consider Cursor for more tweets
        fetched_tweets = api.search_tweets(q=keywords, lang="en", tweet_mode='extended', count=count)
        
        for tweet in fetched_tweets:
            text = tweet.full_text
            screen_name = tweet.user.screen_name
            created_at = tweet.created_at
            retweet_count = tweet.retweet_count
            favorite_count = tweet.favorite_count
            
            sentiment = get_sentiment(text)
            
            tweets_data.append({
                'text': text,
                'user': screen_name,
                'created_at': created_at.isoformat(),
                'retweets': retweet_count,
                'likes': favorite_count,
                'sentiment': sentiment
            })
    except Exception as e:
        print(f"Error fetching tweets: {e}")
    
    return tweets_data

@app.route('/')
def home():
    return "Hello from Twitter Sentiment Analyzer!"

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    keywords = data.get('keywords', '')
    if not keywords:
        return jsonify({"error": "Keywords are required"}), 400

    tweets = get_tweets(keywords)

    if not tweets:
        return jsonify({"error": "Could not fetch tweets or no tweets found for the given keywords."}), 404

    # Analyze sentiment for collected tweets and calculate results
    positive_count = sum(1 for t in tweets if t['sentiment'] == 'positive')
    negative_count = sum(1 for t in tweets if t['sentiment'] == 'negative')
    neutral_count = sum(1 for t in tweets if t['sentiment'] == 'neutral')
    total_tweets = len(tweets)

    # Calculate average sentiment score (simplified)
    sentiment_scores = [sia.polarity_scores(t['text'])['compound'] for t in tweets]
    average_sentiment = sum(sentiment_scores) / total_tweets if total_tweets > 0 else 0

    results = {
        "keywords": keywords,
        "positive": positive_count,
        "negative": negative_count,
        "neutral": neutral_count,
        "total": total_tweets,
        "average_sentiment": round(average_sentiment, 4), # Round for readability
        "tweets": tweets
    }
    return jsonify(results)

if __name__ == '__main__':
    # Consider using environment variables for host and port in production
    app.run(debug=True, host='0.0.0.0', port=5000)
