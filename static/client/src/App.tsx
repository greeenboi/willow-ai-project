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
  const [websocket, setWebsocket] = useState<WebSocket | null>(null);
  const [connectionStatus, setConnectionStatus] = useState('Connecting...');
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

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionId = useRef(Math.random().toString(36).substring(2, 15));
  const chatMessagesRef = useRef<HTMLDivElement>(null);

  // Connect WebSocket
  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/ws/${sessionId.current}`);

    ws.onopen = () => {
      console.log('WebSocket connection established');
      setConnectionStatus('Connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'agent_response') {
        const newMessage: Message = {
          text: data.text,
          sender: 'agent',
          timestamp: new Date().toISOString(),
        };

        setMessages(prevMessages => [...prevMessages, newMessage]);

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
      } else if (data.type === 'error') {
        console.error(data.message);
        setConnectionStatus(`Error: ${data.message}`);
      }
    };

    ws.onclose = (event) => {
      if (event.wasClean) {
        console.log(`Connection closed cleanly, code=${event.code} reason=${event.reason}`);
      } else {
        console.error('Connection died');
        setConnectionStatus('Disconnected. Reconnecting...');
        // Try to reconnect
        setTimeout(() => {
          setWebsocket(new WebSocket(`ws://${window.location.host}/ws/${sessionId.current}`));
        }, 3000);
      }
    };

    ws.onerror = (error) => {
      console.error(`WebSocket error: ${error}`);
      setConnectionStatus('Connection error');
    };

    setWebsocket(ws);

    return () => {
      ws.close();
    };
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

        // Convert blob to base64
        const reader = new FileReader();
        reader.readAsDataURL(audioBlob);
        reader.onloadend = () => {
          const base64data = reader.result as string;

          // Send to server
          if (websocket && websocket.readyState === WebSocket.OPEN) {
            const newMessage: Message = {
              text: '🎤 [Voice message sent]',
              sender: 'user',
              timestamp: new Date().toISOString(),
            };
            setMessages(prevMessages => [...prevMessages, newMessage]);
            websocket.send(JSON.stringify({ audio: base64data }));
          }
        };
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
  const sendMessage = () => {
    if (inputMessage.trim() && websocket && websocket.readyState === WebSocket.OPEN) {
      const newMessage: Message = {
        text: inputMessage.trim(),
        sender: 'user',
        timestamp: new Date().toISOString(),
      };

      setMessages(prevMessages => [...prevMessages, newMessage]);
      websocket.send(JSON.stringify({ text: inputMessage.trim() }));
      setInputMessage('');
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
  }, [messages]);

  // Display media based on type
  const renderMedia = () => {
    if (!currentMedia) return (
      <div className="flex flex-col items-center justify-center h-[300px] text-gray-500">
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
          <circle cx="8.5" cy="8.5" r="1.5"></circle>
          <polyline points="21 15 16 10 5 21"></polyline>
        </svg>
        <p className="mt-3">Relevant media will appear here during the conversation</p>
      </div>
    );

    const { type, topic } = currentMedia;

    if (type === 'demo' || type === 'features') {
      return (
        <div className="flex flex-col">
          <video src={`/static/media/${type}_${topic || 'general'}.mp4`} controls className="max-w-full rounded-md"></video>
          <h3 className="text-center mt-2 font-medium">{topic ? `${type}: ${topic}` : type}</h3>
        </div>
      );
    } else if (type === 'pricing' || type === 'testimonials') {
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
              {messages.map((message, index) => (
                <div key={index} className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
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
                  className="pr-12"
                />
                <div
                  className={`absolute right-2 cursor-pointer p-2 rounded-full transition-all ${isRecording ? 'bg-red-100 text-red-500 animate-pulse' : 'hover:bg-gray-100'}`}
                  onClick={toggleRecording}
                >
                  {isRecording ? <MicOff size={18} /> : <Mic size={18} />}
                </div>
              </div>
              <Button onClick={sendMessage}>
                <Send size={18} className="mr-2" /> Send
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
                  <TabsTrigger value="media" className="flex-1">Media</TabsTrigger>
                  <TabsTrigger value="lead" className="flex-1">Lead Info</TabsTrigger>
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
