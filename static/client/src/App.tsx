import { useState, useEffect, useRef } from 'react';
import './App.css';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Mic, Send, MicOff } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';

interface Message {
  text: string;
  sender: 'user' | 'agent';
  timestamp: string;
}

interface LeadInfo {
  company_name: string | null;
  domain: string | null;
  problem: string | null;
  budget: string | null;
}

interface Media {
  type: string;
  topic: string;
}

function App() {
  // State management
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [connectionStatus, setConnectionStatus] = useState('Initializing...');
  const [isRecording, setIsRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [audioChunks, setAudioChunks] = useState<Blob[]>([]);
  const [leadInfo, setLeadInfo] = useState<LeadInfo>({
    company_name: null,
    domain: null,
    problem: null,
    budget: null,
  });
  const [currentMedia, setCurrentMedia] = useState<Media | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionId = useRef(Math.random().toString(36).substring(2, 15));
  const chatMessagesRef = useRef<HTMLDivElement>(null);

  // Initialize session on component mount
  useEffect(() => {
    const initializeSession = async () => {
      try {
        setConnectionStatus('Connecting...');
        const response = await fetch(`http://localhost:8000/api/session/${sessionId.current}/start`);
        
        if (response.ok) {
          const data = await response.json();
          
          if (data.type === 'agent_response') {
            const newMessage: Message = {
              text: data.text,
              sender: 'agent',
              timestamp: new Date().toISOString(),
            };
            
            setMessages([newMessage]);
            setConnectionStatus('Ready');
            
            // Play initial greeting audio
            if (data.audio) {
              playAudio(data.audio);
            }
            
            // Update lead info if available
            if (data.lead_info) {
              setLeadInfo(data.lead_info);
            }
          }
        } else {
          setConnectionStatus('Failed to connect');
        }
      } catch (error) {
        console.error('Failed to initialize session:', error);
        setConnectionStatus('Connection error');
      }
    };

    initializeSession();
  }, []);

  // Initialize microphone recording
  const initializeRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);

      recorder.ondataavailable = (event) => {
        setAudioChunks(chunks => [...chunks, event.data]);
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        setAudioChunks([]);

        // Send audio to server using HTTP
        try {
          setIsLoading(true);
          const formData = new FormData();
          formData.append('session_id', sessionId.current);
          formData.append('audio_file', audioBlob, 'audio.wav');

          const newMessage: Message = {
            text: '🎤 [Voice message sent]',
            sender: 'user',
            timestamp: new Date().toISOString(),
          };
          setMessages(prevMessages => [...prevMessages, newMessage]);

          const response = await fetch('http://localhost:8000/api/chat/audio', {
            method: 'POST',
            body: formData,
          });

          if (response.ok) {
            const data = await response.json();
            
            if (data.type === 'agent_response') {
              const agentMessage: Message = {
                text: data.text,
                sender: 'agent',
                timestamp: new Date().toISOString(),
              };
              
              setMessages(prevMessages => [...prevMessages, agentMessage]);
              
              // Play audio if available
              if (data.audio) {
                playAudio(data.audio);
              }
              
              // Update lead info if available
              if (data.lead_info) {
                setLeadInfo(data.lead_info);
              }
              
              // Update media if available
              if (data.media) {
                setCurrentMedia(data.media);
              }
              
              // Show transcript if available
              if (data.transcript) {
                console.log('Transcript:', data.transcript);
              }
            }
          } else {
            console.error('Failed to send audio message');
          }
        } catch (error) {
          console.error('Error sending audio:', error);
        } finally {
          setIsLoading(false);
        }
      };

      setMediaRecorder(recorder);
      return true;
    } catch (error) {
      console.error('Error accessing microphone:', error);
      alert('Could not access your microphone. Please check your permissions.');
      return false;
    }
  };

  // Toggle recording
  const toggleRecording = async () => {
    if (isRecording && mediaRecorder) {
      mediaRecorder.stop();
      setIsRecording(false);
    } else {
      if (!mediaRecorder) {
        const initialized = await initializeRecording();
        if (!initialized) return;
      }

      setAudioChunks([]);
      mediaRecorder?.start();
      setIsRecording(true);
    }
  };

  // Play audio from base64 string
  const playAudio = (base64Audio: string) => {
    if (!base64Audio) return;

    const audio = new Audio(`data:audio/wav;base64,${base64Audio}`);
    audio.play();
  };

  // Send a message
  const sendMessage = async () => {
    if (inputMessage.trim() && !isLoading) {
      try {
        setIsLoading(true);
        
        const newMessage: Message = {
          text: inputMessage.trim(),
          sender: 'user',
          timestamp: new Date().toISOString(),
        };

        setMessages(prevMessages => [...prevMessages, newMessage]);
        
        const messageText = inputMessage.trim();
        setInputMessage('');

        // Send message to HTTP endpoint
        const response = await fetch('http://localhost:8000/api/chat/text', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: sessionId.current,
            message: messageText
          }),
        });

        if (response.ok) {
          const data = await response.json();
          
          if (data.type === 'agent_response') {
            const agentMessage: Message = {
              text: data.text,
              sender: 'agent',
              timestamp: new Date().toISOString(),
            };
            
            setMessages(prevMessages => [...prevMessages, agentMessage]);
            
            // Play audio if available
            if (data.audio) {
              playAudio(data.audio);
            }
            
            // Update lead info if available
            if (data.lead_info) {
              setLeadInfo(data.lead_info);
            }
            
            // Update media if available
            if (data.media) {
              setCurrentMedia(data.media);
            }
          }
        } else {
          console.error('Failed to send text message');
          // Add error message to chat
          const errorMessage: Message = {
            text: 'Failed to send message. Please try again.',
            sender: 'agent',
            timestamp: new Date().toISOString(),
          };
          setMessages(prevMessages => [...prevMessages, errorMessage]);
        }
      } catch (error) {
        console.error('Error sending message:', error);
        // Add error message to chat
        const errorMessage: Message = {
          text: 'Connection error. Please try again.',
          sender: 'agent',
          timestamp: new Date().toISOString(),
        };
        setMessages(prevMessages => [...prevMessages, errorMessage]);
      } finally {
        setIsLoading(false);
      }
    }
  };

  // Handle Enter key press
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      sendMessage();
    }
  };

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Display media based on type
  const renderMedia = () => {
    if (!currentMedia) return (
      <div className="flex flex-col items-center justify-center h-[300px] text-gray-500">
        {/* biome-ignore lint/a11y/noSvgWithoutTitle: not needed here */}
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-label="Media placeholder icon">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <polyline points="21 15 16 10 5 21"/>
        </svg>
        <p className="mt-3">Relevant media will appear here during the conversation</p>
      </div>
    );

    const { type, topic } = currentMedia;

    if (type === 'demo' || type === 'features') {
      return (
        <div className="flex flex-col">
          <video src={`/static/media/${type}_${topic || 'general'}.mp4`} controls className="max-w-full rounded-md">
            <track kind="captions" src={`/static/media/captions_${type}_${topic || 'general'}.vtt`} label="English" />
          </video>
          <h3 className="text-center mt-2 font-medium">{topic ? `${type}: ${topic}` : type}</h3>
        </div>
      );
    } 
    if (type === 'pricing' || type === 'testimonials') {
      return (
        <div className="flex flex-col">
          <img src={`/static/media/${type}_${topic || 'general'}.jpg`} alt={`${type} information`} className="max-w-full rounded-md object-contain" />
          <h3 className="text-center mt-2 font-medium">{topic ? `${type}: ${topic}` : type}</h3>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="container mx-auto p-4 min-h-screen flex flex-col">
      <header className="text-center mb-6">
        <h1 className="text-3xl font-bold mb-2">AI Sales Development Representative</h1>
        <p className="text-gray-600">Have a conversation with our AI agent to discuss your needs</p>
      </header>

      <div className="flex flex-1 gap-4 mb-4 flex-col md:flex-row">
        <Card className="flex-1 flex flex-col">
          <CardHeader className="px-4 py-3">
            <CardTitle>Chat with SDR Agent</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1 p-0">
            <div ref={chatMessagesRef} className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((message) => (
                <div key={message.timestamp} className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`px-4 py-2 rounded-lg max-w-[80%] ${message.sender === 'user' ? 'bg-blue-500 text-white' : 'bg-gray-100'}`}>
                    {message.text}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
            <div className="border-t p-4 flex gap-2">
              <div className="flex-1 flex items-center relative">
                <Input
                  type="text"
                  placeholder="Type your message..."
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  disabled={isLoading}
                  className="pr-12"
                />
                <div
                  className={`absolute right-2 cursor-pointer p-2 rounded-full transition-all ${
                    isRecording 
                      ? 'bg-red-100 text-red-500 animate-pulse' 
                      : isLoading
                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'hover:bg-gray-100'
                  }`}
                  onClick={isLoading ? undefined : toggleRecording}
                  onKeyDown={(e) => {
                    if (!isLoading && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault();
                      toggleRecording();
                    }
                  }}
                  aria-label={isRecording ? 'Stop recording' : 'Start recording'}
                >
                  {isRecording ? <MicOff size={18} /> : <Mic size={18} />}
                </div>
              </div>
              <Button onClick={sendMessage} disabled={isLoading || !inputMessage.trim()}>
                <Send size={18} className="mr-2" /> 
                {isLoading ? 'Sending...' : 'Send'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="w-full md:w-[350px] space-y-4">
          <Card>
            <CardHeader className="px-4 py-3">
              <CardTitle>Information</CardTitle>
              <p className="text-xs text-muted-foreground">{connectionStatus}</p>
            </CardHeader>
            <CardContent className="p-4">
              <Tabs defaultValue="media">
                <TabsList className="w-full mb-4">
                  <TabsTrigger value="media" className="flex-1 text-white">Media</TabsTrigger>
                  <TabsTrigger value="lead" className="flex-1 text-white">Lead Info</TabsTrigger>
                </TabsList>
                <TabsContent value="media" className="mt-0">
                  <div className="h-[300px] flex items-center justify-center bg-gray-50 rounded-md overflow-hidden">
                    {renderMedia()}
                  </div>
                </TabsContent>
                <TabsContent value="lead" className="mt-0">
                  <div className="space-y-3 p-3 border rounded-md">
                    <p><strong>Company:</strong> {leadInfo.company_name || "Not provided yet"}</p>
                    <p><strong>Domain:</strong> {leadInfo.domain || "Not provided yet"}</p>
                    <p><strong>Problem:</strong> {leadInfo.problem || "Not provided yet"}</p>
                    <p><strong>Budget:</strong> {leadInfo.budget || "Not provided yet"}</p>
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default App;
