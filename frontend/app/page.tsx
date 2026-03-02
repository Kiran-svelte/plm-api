'use client'

import Link from 'next/link'

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <header className="container mx-auto px-6 py-6">
        <nav className="flex items-center justify-between">
          <div className="text-2xl font-bold text-indigo-600">PLM Enterprise</div>
          <div className="flex items-center space-x-4">
            <Link href="/login" className="text-gray-700 hover:text-indigo-600 font-medium">
              Sign In
            </Link>
            <Link
              href="/signup"
              className="px-5 py-2 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition"
            >
              Get Started
            </Link>
          </div>
        </nav>
      </header>

      {/* Hero Section */}
      <main className="container mx-auto px-6 py-20">
        <div className="text-center max-w-4xl mx-auto">
          <h1 className="text-6xl font-bold text-gray-900 mb-6">
            Private Language Models
            <span className="block text-indigo-600 mt-2">Trained for YOUR Niche</span>
          </h1>

          <p className="text-xl text-gray-600 mb-8">
            Get AI models more expert than general-purpose LLMs in your specific domain.
            Healthcare, Finance, Legal, Crypto - trained exclusively on your data with
            continuous learning from every interaction.
          </p>

          <div className="flex items-center justify-center gap-4 mb-12">
            <div className="bg-white px-6 py-3 rounded-lg shadow-md">
              <div className="text-sm text-gray-500">Starter</div>
              <div className="text-3xl font-bold text-indigo-600">$49</div>
              <div className="text-sm text-gray-500">per month</div>
            </div>
            <div className="bg-white px-6 py-3 rounded-lg shadow-md ring-2 ring-indigo-500">
              <div className="text-sm text-gray-500">Professional</div>
              <div className="text-3xl font-bold text-indigo-600">$199</div>
              <div className="text-sm text-gray-500">per month</div>
            </div>
            <div className="bg-white px-6 py-3 rounded-lg shadow-md">
              <div className="text-sm text-gray-500">Enterprise</div>
              <div className="text-3xl font-bold text-indigo-600">$499</div>
              <div className="text-sm text-gray-500">per month</div>
            </div>
          </div>

          <div className="flex justify-center gap-4">
            <Link
              href="/signup"
              className="px-8 py-4 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition text-lg"
            >
              Start Building
            </Link>
            <Link
              href="/login"
              className="px-8 py-4 bg-white text-indigo-600 rounded-lg font-semibold hover:bg-gray-50 transition text-lg border-2 border-indigo-600"
            >
              Sign In
            </Link>
          </div>
        </div>

        {/* Features */}
        <div className="mt-24 grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          <div className="bg-white p-8 rounded-xl shadow-lg">
            <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="text-xl font-bold mb-3">Niche Expert</h3>
            <p className="text-gray-600">
              Intelligent knowledge base trained on your domain. Medical diagnosis, legal contracts,
              crypto trading - your model knows your field inside and out.
            </p>
          </div>

          <div className="bg-white p-8 rounded-xl shadow-lg">
            <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <h3 className="text-xl font-bold mb-3">Multi-Model Fact Checking</h3>
            <p className="text-gray-600">
              Every response verified through multi-model consensus. Cross-validation
              ensures accuracy and prevents hallucinations.
            </p>
          </div>

          <div className="bg-white p-8 rounded-xl shadow-lg">
            <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <h3 className="text-xl font-bold mb-3">Learns Forever</h3>
            <p className="text-gray-600">
              Continuously improves from every interaction. Good responses strengthen
              the knowledge base. Your AI gets smarter every day.
            </p>
          </div>
        </div>

        {/* How It Works */}
        <div className="mt-24 max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">How It Works</h2>
          <div className="grid md:grid-cols-4 gap-6">
            {[
              { step: '1', title: 'Sign Up', desc: 'Create your account and set up your organization' },
              { step: '2', title: 'Choose Niche', desc: 'Select your domain and initial topics' },
              { step: '3', title: 'Auto-Train', desc: 'We generate domain data and build your knowledge base' },
              { step: '4', title: 'Query & Learn', desc: 'Use your model - it learns from every interaction' },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="w-10 h-10 bg-indigo-600 text-white rounded-full flex items-center justify-center mx-auto mb-3 font-bold">
                  {item.step}
                </div>
                <h4 className="font-semibold mb-1">{item.title}</h4>
                <p className="text-sm text-gray-600">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Social Proof */}
        <div className="mt-24 text-center">
          <p className="text-gray-500 mb-4">BUILT FOR DOMAINS IN</p>
          <div className="flex flex-wrap justify-center gap-4 text-sm">
            {['Healthcare AI', 'Cryptocurrency', 'Legal Tech', 'Finance', 'Education', 'DevTools', 'Marketing'].map(
              (domain) => (
                <span key={domain} className="px-4 py-2 bg-white rounded-full shadow-sm font-medium text-gray-700">
                  {domain}
                </span>
              )
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="container mx-auto px-6 py-12 text-center text-gray-600">
        <p>PLM Enterprise - Private Language Models for every domain.</p>
      </footer>
    </div>
  )
}
