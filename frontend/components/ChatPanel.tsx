'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useStore, type Conversation, type Message, type Assistant } from '@/lib/store'
import type { Modality } from '@/components/ModalitySelector'
import {
  getConversations,
  getConversation,
  createConversation,
  deleteConversation,
  sendMessageStream,
  updateConversation,
  getAssistants,
  togglePrivacyMode,
  toggleAutoLearning,
  getModelPhase,
} from '@/lib/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ---------------------------------------------------------------------------
// Code block with copy button
// ---------------------------------------------------------------------------

function CodeBlock({ children, className }: { children: React.ReactNode; className?: string }) {
  const [copied, setCopied] = useState(false)
  const lang = className?.replace('language-', '') || ''
  const codeText = String(children).replace(/\n$/, '')

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback
      const ta = document.createElement('textarea')
      ta.value = codeText
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="relative group my-3 rounded-xl overflow-hidden bg-gray-900">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <span className="text-xs text-gray-400 font-mono">{lang || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-white rounded hover:bg-gray-700 transition"
        >
          {copied ? (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Copied
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                />
              </svg>
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-sm leading-relaxed">
        <code className={`text-gray-100 ${className || ''}`}>{codeText}</code>
      </pre>
    </div>
  )
}

// Inline code
function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="px-1.5 py-0.5 bg-gray-100 text-indigo-700 rounded text-[0.85em] font-mono border border-gray-200">
      {children}
    </code>
  )
}

// ---------------------------------------------------------------------------
// Markdown renderer for assistant messages
// ---------------------------------------------------------------------------

function MarkdownContent({ content, isStreaming }: { content: string; isStreaming?: boolean }) {
  return (
    <div className="prose prose-sm max-w-none prose-gray prose-headings:text-gray-800 prose-headings:font-semibold prose-p:leading-relaxed prose-pre:p-0 prose-pre:bg-transparent prose-code:before:content-[''] prose-code:after:content-['']">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const isBlock = className?.startsWith('language-') || String(children).includes('\n')
            if (isBlock) {
              return <CodeBlock className={className}>{children}</CodeBlock>
            }
            return <InlineCode>{children}</InlineCode>
          },
          pre({ children }) {
            return <>{children}</>
          },
          a({ href, children }) {
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:text-indigo-700 underline">
                {children}
              </a>
            )
          },
          table({ children }) {
            return (
              <div className="overflow-x-auto my-3 rounded-lg border border-gray-200">
                <table className="min-w-full text-sm">{children}</table>
              </div>
            )
          },
          th({ children }) {
            return <th className="px-3 py-2 bg-gray-50 text-left font-semibold text-gray-700 border-b border-gray-200">{children}</th>
          },
          td({ children }) {
            return <td className="px-3 py-2 border-b border-gray-100">{children}</td>
          },
          ul({ children }) {
            return <ul className="list-disc pl-5 space-y-1 my-2">{children}</ul>
          },
          ol({ children }) {
            return <ol className="list-decimal pl-5 space-y-1 my-2">{children}</ol>
          },
          blockquote({ children }) {
            return <blockquote className="border-l-4 border-indigo-300 pl-4 italic text-gray-600 my-3">{children}</blockquote>
          },
        }}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && <span className="inline-block w-1.5 h-4 bg-indigo-500 ml-0.5 animate-pulse align-middle" />}
    </div>
  )
}

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 86400000) return 'Today'
  if (diff < 172800000) return 'Yesterday'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// ---------------------------------------------------------------------------
// Per-modality helpers
// ---------------------------------------------------------------------------

const MODALITY_PLACEHOLDERS: Record<Modality, string> = {
  text: 'Type your message… (Enter to send, Shift+Enter for newline)',
  code: 'Describe the code you want to generate, review, or explain…',
  image: 'Describe the image you want analyzed, or paste an image URL…',
  voice: 'Describe the voice script or spoken-word content you need…',
}

const MODALITY_BADGES: Record<Modality, string> = {
  text: '',
  code: '⌨️ Code',
  image: '🖼️ Image',
  voice: '🎙️ Voice',
}

interface ChatPanelProps {
  /** Active input modality — controls routing and UI hints */
  modality?: Modality
}

export default function ChatPanel({ modality = 'text' }: ChatPanelProps) {
  const {
    selectedOrg,
    selectedModel,
    conversations,
    selectedConversation,
    messages,
    assistants,
    modelPhase,
    setModelPhase,
    setConversations,
    setSelectedConversation,
    setMessages,
    setAssistants,
  } = useStore()

  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const [useRag, setUseRag] = useState(true)
  const [temperature, setTemperature] = useState(0.7)
  const [showSettings, setShowSettings] = useState(false)
  const [editingTitle, setEditingTitle] = useState<string | null>(null)
  const [titleInput, setTitleInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showAssistantPicker, setShowAssistantPicker] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Fetch conversations when org changes
  const fetchConversations = useCallback(async () => {
    if (!selectedOrg) return
    try {
      const res = await getConversations(selectedOrg.id)
      setConversations(res.data.conversations ?? res.data ?? [])
    } catch {
      console.error('Failed to fetch conversations')
    }
  }, [selectedOrg, setConversations])

  useEffect(() => {
    fetchConversations()
  }, [fetchConversations])

  // Fetch assistants when org changes
  useEffect(() => {
    if (!selectedOrg) return
    ;(async () => {
      try {
        const res = await getAssistants(selectedOrg.id)
        setAssistants(res.data.assistants ?? res.data ?? [])
      } catch {
        console.error('Failed to fetch assistants')
      }
    })()
  }, [selectedOrg, setAssistants])

  // Fetch model phase so privacy indicator works on Chat tab
  useEffect(() => {
    if (!selectedOrg?.id || !selectedModel?.id) return
    const fetchPhase = async () => {
      try {
        const res = await getModelPhase(selectedOrg.id, selectedModel.id)
        setModelPhase(res.data)
      } catch {
        // Phase info is supplementary — don't block chat
      }
    }
    fetchPhase()
    const interval = setInterval(fetchPhase, 15000)
    return () => clearInterval(interval)
  }, [selectedOrg?.id, selectedModel?.id, setModelPhase])

  // Fetch messages when conversation changes
  useEffect(() => {
    if (!selectedOrg || !selectedConversation) {
      setMessages([])
      return
    }
    ;(async () => {
      try {
        const res = await getConversation(selectedOrg.id, selectedConversation.id)
        setMessages(res.data.messages ?? [])
      } catch {
        console.error('Failed to fetch messages')
      }
    })()
  }, [selectedOrg, selectedConversation?.id, setMessages])

  // Auto-scroll to bottom on new messages or streaming content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  // Auto-resize textarea
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }

  const handleNewChat = async (assistant?: Assistant) => {
    if (!selectedOrg) return
    setShowAssistantPicker(false)
    try {
      const res = await createConversation(selectedOrg.id, {
        model_id: selectedModel?.id,
        assistant_id: assistant?.id,
      })
      const newConv = res.data as Conversation
      setConversations([newConv, ...conversations])
      setSelectedConversation(newConv)
      setMessages([])
      textareaRef.current?.focus()
    } catch {
      setError('Failed to create conversation')
    }
  }

  const getAssistantForConversation = (conv: Conversation): Assistant | undefined => {
    if (!conv.assistant_id) return undefined
    return assistants.find(a => a.id === conv.assistant_id)
  }

  const assistantIconMap: Record<string, string> = {
    brain: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
    search: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
    sparkles: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z',
    code: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4',
    support: 'M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z',
  }

  const handleSelectConversation = (conv: Conversation) => {
    setSelectedConversation(conv)
    setError(null)
  }

  const handleDeleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!selectedOrg) return
    try {
      await deleteConversation(selectedOrg.id, convId)
      setConversations(conversations.filter((c) => c.id !== convId))
      if (selectedConversation?.id === convId) {
        setSelectedConversation(null)
        setMessages([])
      }
    } catch {
      setError('Failed to delete conversation')
    }
  }

  const handleRenameConversation = async (convId: string) => {
    if (!selectedOrg || !titleInput.trim()) return
    try {
      await updateConversation(selectedOrg.id, convId, { title: titleInput.trim() })
      setConversations(
        conversations.map((c) =>
          c.id === convId ? { ...c, title: titleInput.trim() } : c
        )
      )
      if (selectedConversation?.id === convId) {
        setSelectedConversation({ ...selectedConversation, title: titleInput.trim() })
      }
    } catch {
      /* ignore */
    }
    setEditingTitle(null)
  }

  const handleSend = async () => {
    if (!selectedOrg || !selectedConversation || !inputText.trim() || sending) return

    const content = inputText.trim()
    setInputText('')
    setSending(true)
    setError(null)
    setStreamingContent('')

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    // Optimistic: add user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: selectedConversation.id,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }
    setMessages([...messages, tempUserMsg])

    let accumulated = ''

    try {
      await sendMessageStream(
        selectedOrg.id,
        selectedConversation.id,
        { content, use_rag: useRag, temperature, modality },
        // onToken
        (token: string) => {
          accumulated += token
          setStreamingContent(accumulated)
        },
        // onDone
        (metadata: any) => {
          const userMsg: Message = metadata.user_message
          const assistantMsg: Message = metadata.assistant_message

          // Replace temp message + streaming state with real messages
          const currentMsgs = useStore.getState().messages
          const filtered = currentMsgs.filter((m) => m.id !== tempUserMsg.id)
          setMessages([...filtered, userMsg, assistantMsg])
          setStreamingContent('')
          setSending(false)
          fetchConversations()
          textareaRef.current?.focus()
          // Signal PetStatus to refresh if a training example was saved
          if (metadata.training_example_saved) {
            // Pet refresh handled by polling
          }
        },
        // onError
        (errMsg: string) => {
          setError(errMsg)
          const errorMsgs = useStore.getState().messages
          setMessages(errorMsgs.filter((m) => m.id !== tempUserMsg.id))
          setStreamingContent('')
          setSending(false)
          textareaRef.current?.focus()
        }
      )
    } catch (err: any) {
      setError(err?.message || 'Failed to send message. Please try again.')
      const errorMsgs = useStore.getState().messages
      setMessages(errorMsgs.filter((m) => m.id !== tempUserMsg.id))
      setStreamingContent('')
      setSending(false)
      textareaRef.current?.focus()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-full -m-4 sm:-m-6 animate-fade-in">
      {/* Conversation sidebar */}
      <div className="w-64 border-r border-gray-200/60 bg-gray-50/80 flex flex-col shrink-0">
        <div className="p-3 border-b border-gray-200/60 relative">
          <button
            onClick={() => {
              if (assistants.length > 0) {
                setShowAssistantPicker(!showAssistantPicker)
              } else {
                handleNewChat()
              }
            }}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-600 to-indigo-700 rounded-xl hover:from-indigo-700 hover:to-indigo-800 transition-all duration-200 shadow-sm hover:shadow-md btn-press"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Chat
          </button>

          {/* Assistant picker dropdown */}
          {showAssistantPicker && (
            <div className="absolute left-3 right-3 top-full mt-1 bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-xl z-20 overflow-hidden animate-scale-in">
              <button
                onClick={() => handleNewChat()}
                className="w-full px-3 py-2.5 text-left text-sm hover:bg-gray-50 border-b border-gray-100 flex items-center gap-2"
              >
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                  />
                </svg>
                <div>
                  <p className="font-medium text-gray-700">Default Chat</p>
                  <p className="text-xs text-gray-400">No assistant</p>
                </div>
              </button>
              {assistants.map((a) => (
                <button
                  key={a.id}
                  onClick={() => handleNewChat(a)}
                  className="w-full px-3 py-2.5 text-left text-sm hover:bg-gray-50 border-b border-gray-100 last:border-b-0 flex items-center gap-2"
                >
                  <svg className="w-4 h-4 text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d={assistantIconMap[a.icon] || assistantIconMap.brain}
                    />
                  </svg>
                  <div className="min-w-0">
                    <p className="font-medium text-gray-700 truncate">{a.name}</p>
                    {a.description && (
                      <p className="text-xs text-gray-400 truncate">{a.description}</p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-0.5 scrollbar-thin">
          {conversations.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8 px-4">
              No conversations yet. Start a new chat!
            </p>
          ) : (
            conversations.map((conv) => {
              const isSelected = selectedConversation?.id === conv.id
              return (
                <div
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv)}
                  className={`group relative px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 ${
                    isSelected
                      ? 'bg-indigo-50 text-indigo-700 shadow-sm'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {editingTitle === conv.id ? (
                    <input
                      type="text"
                      value={titleInput}
                      onChange={(e) => setTitleInput(e.target.value)}
                      onBlur={() => handleRenameConversation(conv.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameConversation(conv.id)
                        if (e.key === 'Escape') setEditingTitle(null)
                      }}
                      autoFocus
                      className="w-full text-sm px-1 py-0.5 border border-indigo-300 rounded focus:outline-none"
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <>
                      <p className="text-sm font-medium truncate pr-12">{conv.title}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{formatDate(conv.updated_at)}</p>
                      <div className="absolute right-2 top-2 hidden group-hover:flex items-center gap-1">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditingTitle(conv.id)
                            setTitleInput(conv.title)
                          }}
                          className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600"
                          title="Rename"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                            />
                          </svg>
                        </button>
                        <button
                          onClick={(e) => handleDeleteConversation(conv.id, e)}
                          className="p-1 rounded hover:bg-red-100 text-gray-400 hover:text-red-600"
                          title="Delete"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          </svg>
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {!selectedConversation ? (
          /* Empty state */
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center px-6">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-indigo-100 flex items-center justify-center">
                <svg className="w-8 h-8 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-1">Start a Conversation</h2>
              <p className="text-sm text-gray-500 mb-6">
                {assistants.length > 0
                  ? 'Choose an assistant to start chatting'
                  : 'Click below to start chatting with your AI model'}
              </p>

              {assistants.length > 0 ? (
                <div className="grid grid-cols-1 gap-2 max-w-sm mx-auto">
                  {assistants.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => handleNewChat(a)}
                      className="flex items-center gap-3 px-4 py-3 bg-white border border-gray-200 rounded-lg hover:border-indigo-300 hover:bg-indigo-50 transition text-left"
                    >
                      <div className="shrink-0 w-9 h-9 rounded-lg bg-indigo-100 flex items-center justify-center">
                        <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d={assistantIconMap[a.icon] || assistantIconMap.brain}
                          />
                        </svg>
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-gray-800">{a.name}</p>
                        {a.description && (
                          <p className="text-xs text-gray-500 truncate">{a.description}</p>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <button
                  onClick={() => handleNewChat()}
                  className="px-6 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition"
                >
                  New Chat
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* Chat header */}
            <div className="px-4 py-3 border-b border-gray-200 bg-white flex items-center justify-between">
              <div className="min-w-0 flex items-center gap-2">
                {(() => {
                  const convAssistant = getAssistantForConversation(selectedConversation)
                  if (convAssistant) {
                    return (
                      <div className="shrink-0 w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
                        <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d={assistantIconMap[convAssistant.icon] || assistantIconMap.brain}
                          />
                        </svg>
                      </div>
                    )
                  }
                  return null
                })()}
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-gray-800 truncate">
                    {selectedConversation.title}
                  </h3>
                  <p className="text-xs text-gray-400">
                    {(() => {
                      const convAssistant = getAssistantForConversation(selectedConversation)
                      if (convAssistant) return convAssistant.name
                      return selectedModel?.name || 'No model selected'
                    })()}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* Privacy mode indicator */}
                {modelPhase && (
                  modelPhase.privacy_mode_available ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      PLM Private
                    </span>
                  ) : modelPhase.phase === 'collecting' || modelPhase.phase === 'learning' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                      PLM Learning
                    </span>
                  ) : modelPhase.phase === 'training' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
                      <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Training
                    </span>
                  ) : null
                )}
                <button
                  onClick={() => setShowSettings(!showSettings)}
                  className={`p-2 rounded-lg transition ${
                    showSettings ? 'bg-indigo-50 text-indigo-600' : 'text-gray-400 hover:bg-gray-100'
                  }`}
                  title="Chat settings"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
                    />
                  </svg>
                </button>
              </div>
            </div>

            {/* Settings bar */}
            {showSettings && (
              <div className="px-4 py-2.5 border-b border-gray-200 bg-gray-50 flex flex-wrap items-center gap-5">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={useRag}
                    onChange={(e) => setUseRag(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-gray-700">Knowledge Context</span>
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-700">Temp:</span>
                  <input
                    type="range"
                    min={0} max={2} step={0.1}
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="w-24 accent-indigo-600"
                  />
                  <span className="text-sm font-mono text-gray-600 w-8">{temperature.toFixed(1)}</span>
                </div>
                {/* Privacy Mode toggle */}
                {modelPhase && (
                  <label className="flex items-center gap-2 cursor-pointer select-none" title={modelPhase.has_adapter ? 'Force all queries through your private fine-tuned model' : 'Requires a deployed model adapter'}>
                    <input
                      type="checkbox"
                      checked={modelPhase.privacy_mode_forced ?? false}
                      disabled={!modelPhase.has_adapter}
                      onChange={async (e) => {
                        if (selectedOrg && selectedModel) {
                          try {
                            await togglePrivacyMode(selectedOrg.id, selectedModel.id, e.target.checked)
                            setModelPhase({ ...modelPhase, privacy_mode_forced: e.target.checked })
                          } catch {}
                        }
                      }}
                      className="w-4 h-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500 disabled:opacity-50"
                    />
                    <span className={`text-sm ${modelPhase.has_adapter ? 'text-gray-700' : 'text-gray-400'}`}>Privacy Mode</span>
                  </label>
                )}
                {/* Auto-Learning toggle */}
                {modelPhase && (
                  <label className="flex items-center gap-2 cursor-pointer select-none" title="Learn from chat interactions to improve the model">
                    <input
                      type="checkbox"
                      checked={modelPhase.auto_learning_enabled ?? true}
                      onChange={async (e) => {
                        if (selectedOrg && selectedModel) {
                          try {
                            await toggleAutoLearning(selectedOrg.id, selectedModel.id, e.target.checked)
                            setModelPhase({ ...modelPhase, auto_learning_enabled: e.target.checked })
                          } catch {}
                        }
                      }}
                      className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm text-gray-700">Auto-Learn</span>
                  </label>
                )}
              </div>
            )}

            {/* Messages area */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scrollbar-thin">
              {messages.length === 0 && !sending && (
                <div className="text-center py-16 animate-fade-in">
                  <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-indigo-100 to-indigo-50 flex items-center justify-center">
                    <svg className="w-7 h-7 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                      />
                    </svg>
                  </div>
                  <p className="text-sm text-gray-400">Send a message to start the conversation</p>
                </div>
              )}

              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-slide-up`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 shadow-sm ${
                      msg.role === 'user'
                        ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white'
                        : 'bg-white border border-gray-100 text-gray-800'
                    }`}
                  >
                    {msg.role === 'assistant' ? (
                      <MarkdownContent content={msg.content} />
                    ) : (
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                    )}
                    <div className={`flex items-center gap-2 mt-1.5 ${
                      msg.role === 'user' ? 'justify-end' : 'justify-between'
                    }`}>
                      <span className={`text-xs ${
                        msg.role === 'user' ? 'text-indigo-200' : 'text-gray-400'
                      }`}>
                        {formatTime(msg.created_at)}
                      </span>
                      {msg.role === 'assistant' && msg.metadata && (
                        <div className="flex items-center gap-2 text-xs text-gray-400">
                          {/* Modality badge for non-text responses */}
                          {msg.metadata.modality && msg.metadata.modality !== 'text' && (
                            <span className="text-violet-500 font-medium">
                              {MODALITY_BADGES[msg.metadata.modality as Modality] || msg.metadata.modality}
                            </span>
                          )}
                          {msg.metadata.privacy_mode ? (
                            <span className="text-emerald-600 font-medium">Private</span>
                          ) : (
                            <span className="text-amber-600">Learning</span>
                          )}
                          {msg.metadata.confidence != null && (
                            <span>{(msg.metadata.confidence * 100).toFixed(0)}%</span>
                          )}
                          {msg.metadata.response_time_ms != null && (
                            <span>{msg.metadata.response_time_ms}ms</span>
                          )}
                          {msg.metadata.context_used && (
                            <span className="text-indigo-400">RAG</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {sending && (
                <div className="flex justify-start animate-slide-up">
                  <div className="bg-white border border-gray-100 rounded-2xl px-4 py-3 max-w-[80%] shadow-sm">
                    {streamingContent ? (
                      <MarkdownContent content={streamingContent} isStreaming />
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Error banner */}
            {error && (
              <div className={`mx-4 mb-2 rounded-lg px-4 py-2 flex items-center justify-between ${
                error.includes('limit') || error.includes('Upgrade')
                  ? 'bg-amber-50 border border-amber-200'
                  : 'bg-red-50 border border-red-200'
              }`}>
                <div className="flex items-center gap-2">
                  <span className={`text-sm ${
                    error.includes('limit') || error.includes('Upgrade')
                      ? 'text-amber-700'
                      : 'text-red-700'
                  }`}>{error}</span>
                  {(error.includes('limit') || error.includes('Upgrade')) && (
                    <a
                      href="/dashboard?tab=settings"
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 whitespace-nowrap"
                    >
                      Upgrade Plan
                    </a>
                  )}
                </div>
                <button onClick={() => setError(null)} className="text-gray-400 hover:text-gray-600 shrink-0">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {/* Learning mode banner */}
            {modelPhase && !modelPhase.privacy_mode_available && (modelPhase.phase === 'collecting' || modelPhase.phase === 'learning') && (
              <div className="mx-4 mt-2 rounded-lg px-3 py-2 bg-amber-50 border border-amber-100 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                <p className="text-xs text-amber-700">
                  Responses use AI APIs while your private model trains. Your chats help improve it.
                  <span className="text-amber-500 ml-1">
                    {modelPhase.progress_pct > 0 ? `${Math.round(modelPhase.progress_pct)}% to first training.` : ''}
                  </span>
                </p>
              </div>
            )}

            {/* Input area */}
            <div className="border-t border-gray-200/60 bg-white/80 backdrop-blur-sm px-4 py-3">
              <div className="flex items-end gap-3">
                <textarea
                  ref={textareaRef}
                  value={inputText}
                  onChange={handleTextareaChange}
                  onKeyDown={handleKeyDown}
                  placeholder={MODALITY_PLACEHOLDERS[modality]}
                  rows={1}
                  className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none bg-gray-50/50 transition-colors"
                  disabled={sending}
                />
                <button
                  onClick={handleSend}
                  disabled={sending || !inputText.trim()}
                  className="shrink-0 p-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white rounded-xl hover:from-indigo-700 hover:to-indigo-800 disabled:from-gray-200 disabled:to-gray-300 disabled:text-gray-400 disabled:cursor-not-allowed transition-all duration-200 shadow-sm hover:shadow-md btn-press"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
