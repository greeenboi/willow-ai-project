import { useState, useEffect, useRef } from 'react';
import './App.css';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Progress } from './components/ui/progress';
import { Avatar, AvatarFallback } from './components/ui/avatar';
import { Mic, Send, MicOff, User, Bot, Building, Globe, AlertCircle, DollarSign, CheckCircle2, Clock, Zap } from 'lucide-react';
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

// LeadInfoCard component for better lead info display
interface LeadInfoCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  placeholder: string;
}

const LeadInfoCard = ({ icon, label, value, placeholder }: LeadInfoCardProps) => {
  const isCompleted = value !== null && value !== "";
  
  return (
    <div className={`p-3 rounded-lg border transition-all ${
      isCompleted 
        ? 'bg-green-50 border-green-200' 
        : 'bg-gray-50 border-gray-200 hover:border-gray-300'
    }`}>
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-full ${
          isCompleted ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
        }`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-medium text-sm text-gray-900">{label}</h4>
            {isCompleted && <CheckCircle2 size={14} className="text-green-500" />}
          </div>
          <p className={`text-sm ${
            isCompleted ? 'text-gray-900 font-medium' : 'text-gray-500 italic'
          }`}>
            {value || placeholder}
          </p>
        </div>
      </div>
    </div>
  );
};

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

  // Helper functions for lead info
  const getFilledFieldsCount = () => {
    return Object.values(leadInfo).filter(value => value !== null && value !== "").length;
  };

  const getCompletionPercentage = () => {
    return (getFilledFieldsCount() / 4) * 100;
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
        <div className="flex items-center justify-center gap-3 mb-3">
          <div className="p-3 bg-blue-100 rounded-full">
            <Bot size={32} className="text-blue-600" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">AI Sales Agent</h1>
            <p className="text-gray-600">Jane - Your AI Sales Development Representative</p>
          </div>
        </div>
        
        {/* Connection Status */}
        <div className="flex items-center justify-center gap-2 mt-4">
          <div className={`w-2 h-2 rounded-full ${
            connectionStatus === 'Ready' ? 'bg-green-500 animate-pulse' :
            connectionStatus === 'Connecting...' ? 'bg-yellow-500 animate-pulse' :
            connectionStatus === 'Initializing...' ? 'bg-blue-500 animate-pulse' :
            'bg-red-500'
          }`} />
          <span className={`text-sm font-medium ${
            connectionStatus === 'Ready' ? 'text-green-600' :
            connectionStatus === 'Connecting...' ? 'text-yellow-600' :
            connectionStatus === 'Initializing...' ? 'text-blue-600' :
            'text-red-600'
          }`}>
            {connectionStatus}
          </span>
          {connectionStatus === 'Ready' && (
            <Zap size={14} className="text-green-500" />
          )}
        </div>
      </header>

      <div className="flex flex-1 gap-4 mb-4 flex-col md:flex-row">
        <Card className="flex-1 flex flex-col">
          <CardHeader className="px-4 py-3">
            <CardTitle>Chat with SDR Agent</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1 p-0">
            <div ref={chatMessagesRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
              {messages.map((message, index) => (
                <div key={`${message.timestamp}-${index}`} className={`flex gap-3 ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {message.sender === 'agent' && (
                    <Avatar className="h-8 w-8 mt-1">
                      <AvatarFallback className="bg-blue-500 text-white text-sm">
                        <Bot size={16} />
                      </AvatarFallback>
                    </Avatar>
                  )}
                  <div className={`flex flex-col max-w-[80%] ${message.sender === 'user' ? 'items-end' : 'items-start'}`}>
                    <div className={`px-4 py-3 rounded-2xl shadow-sm ${
                      message.sender === 'user' 
                        ? 'bg-blue-500 text-white rounded-br-md' 
                        : 'bg-white border border-gray-200 rounded-bl-md'
                    }`}>
                      <p className="text-sm leading-relaxed">{message.text}</p>
                    </div>
                    <span className="text-xs text-gray-500 mt-1 px-2">
                      {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  {message.sender === 'user' && (
                    <Avatar className="h-8 w-8 mt-1">
                      <AvatarFallback className="bg-green-500 text-white text-sm">
                        <User size={16} />
                      </AvatarFallback>
                    </Avatar>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
            <div className="border-t bg-white p-4">
              <div className="flex gap-3 items-end">
                <div className="flex-1 relative">
                  <Input
                    type="text"
                    placeholder={isLoading ? "Processing..." : "Type your message or click the mic to speak..."}
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    disabled={isLoading}
                    className="pr-12 py-3 rounded-full border-2 focus:border-blue-500 transition-all"
                  />
                  <button
                    className={`absolute right-3 top-1/2 transform -translate-y-1/2 p-2 rounded-full transition-all ${
                      isRecording 
                        ? 'bg-red-100 text-red-500 animate-pulse shadow-lg' 
                        : isLoading
                          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                          : 'hover:bg-gray-100 text-gray-600 hover:text-blue-600'
                    }`}
                    onClick={isLoading ? undefined : toggleRecording}
                    disabled={isLoading}
                    type='button'
                    onKeyDown={(e) => {
                      if (!isLoading && (e.key === 'Enter' || e.key === ' ')) {
                        e.preventDefault();
                        toggleRecording();
                      }
                    }}
                    aria-label={isRecording ? 'Stop recording' : 'Start recording'}
                  >
                    {isRecording ? <MicOff size={20} /> : <Mic size={20} />}
                  </button>
                </div>
                <Button 
                  onClick={sendMessage} 
                  disabled={isLoading || !inputMessage.trim()}
                  className={`px-6 py-3 rounded-full transition-all ${
                    isLoading 
                      ? 'bg-gray-400 cursor-not-allowed' 
                      : 'bg-blue-500 hover:bg-blue-600 shadow-lg hover:shadow-xl'
                  }`}
                >
                  {isLoading ? (
                    <>
                      <Clock size={18} className="mr-2 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    <>
                      <Send size={18} className="mr-2" /> 
                      Send
                    </>
                  )}
                </Button>
              </div>
              {isRecording && (
                <div className="mt-3 flex items-center justify-center gap-2 text-red-500">
                  <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                  <span className="text-sm font-medium">Recording... Click mic to stop</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="w-full md:w-[380px] space-y-4">
          <Card className="shadow-lg border-0 bg-gradient-to-br from-white to-gray-50">
            <CardHeader className="px-4 py-3">
              <CardTitle className="flex items-center gap-2">
                <Bot size={20} className="text-blue-600" />
                Session Information
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <Tabs defaultValue="lead" className="w-full">
                <TabsList className="grid w-full grid-cols-2 mb-4 bg-gray-100">
                  <TabsTrigger value="lead" className="flex items-center gap-2 data-[state=active]:bg-white">
                    <User size={16} />
                    Lead Info
                  </TabsTrigger>
                  <TabsTrigger value="media" className="flex items-center gap-2 data-[state=active]:bg-white">
                    <Globe size={16} />
                    Media
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="media" className="mt-0">
                  <div className="bg-gray-50 rounded-lg border-2 border-dashed border-gray-200 overflow-hidden">
                    {currentMedia ? (
                      <div className="p-4">
                        <div className="mb-3 flex items-center gap-2">
                          <Badge variant="secondary" className="text-xs">
                            {currentMedia.type.toUpperCase()}
                          </Badge>
                          <span className="text-sm text-gray-600">{currentMedia.topic}</span>
                        </div>
                        {renderMedia()}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center h-[300px] text-gray-500 p-6">
                        <div className="w-16 h-16 bg-gray-200 rounded-full flex items-center justify-center mb-3">
                          <Globe size={24} />
                        </div>
                        <h3 className="font-medium mb-2">Media Display</h3>
                        <p className="text-center text-sm leading-relaxed">
                          Relevant images and videos will appear here based on your conversation context
                        </p>
                      </div>
                    )}
                  </div>
                </TabsContent>
                <TabsContent value="lead" className="mt-0">
                  <div className="space-y-4">
                    {/* Progress Overview */}
                    <div className="p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="font-medium text-gray-900">Lead Qualification Progress</h3>
                        <Badge variant={getCompletionPercentage() === 100 ? "default" : "secondary"}>
                          {getCompletionPercentage()}% Complete
                        </Badge>
                      </div>
                      <Progress value={getCompletionPercentage()} className="h-2" />
                      <p className="text-xs text-gray-600 mt-2">
                        {getCompletionPercentage() === 100 
                          ? "All information collected! Ready for handoff." 
                          : `${4 - getFilledFieldsCount()} fields remaining`}
                      </p>
                    </div>

                    {/* Lead Information Cards */}
                    <div className="space-y-3">
                      <LeadInfoCard
                        icon={<Building size={16} />}
                        label="Company"
                        value={leadInfo.company_name}
                        placeholder="Company name not provided yet"
                      />
                      <LeadInfoCard
                        icon={<Globe size={16} />}
                        label="Domain/Industry"
                        value={leadInfo.domain}
                        placeholder="Industry not specified yet"
                      />
                      <LeadInfoCard
                        icon={<AlertCircle size={16} />}
                        label="Problem/Challenge"
                        value={leadInfo.problem}
                        placeholder="Problem statement not shared yet"
                      />
                      <LeadInfoCard
                        icon={<DollarSign size={16} />}
                        label="Budget"
                        value={leadInfo.budget}
                        placeholder="Budget information not discussed yet"
                      />
                    </div>

                    {/* Action Buttons */}
                    {getCompletionPercentage() === 100 && (
                      <div className="pt-4 border-t">
                        <Button className="w-full bg-green-600 hover:bg-green-700">
                          <CheckCircle2 size={16} className="mr-2" />
                          Mark as Qualified Lead
                        </Button>
                      </div>
                    )}
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
