import { useState, useEffect, useRef } from 'react';
import './App.css';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Progress } from './components/ui/progress';
import { Avatar, AvatarFallback, AvatarImage } from './components/ui/avatar';
import { Mic, Send, MicOff, User, Bot, Building, Globe, AlertCircle, DollarSign, CheckCircle2, Loader2 } from 'lucide-react';
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
    <div className={`p-3 rounded-lg border transition-all backdrop-blur-sm ${
      isCompleted 
        ? 'bg-green-500/20 border-green-400/30 text-green-300' 
        : 'bg-white/5 border-white/20 hover:border-white/30 text-white/70'
    }`}>
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-full ${
          isCompleted ? 'bg-green-500/30 text-green-300' : 'bg-white/10 text-white/60'
        }`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className={`font-medium text-sm ${isCompleted ? 'text-green-300' : 'text-white'}`}>{label}</h4>
            {isCompleted && <CheckCircle2 size={14} className="text-green-400" />}
          </div>
          <p className={`text-sm ${
            isCompleted ? 'text-green-200 font-medium' : 'text-white/50 italic'
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
  const audioChunksRef = useRef<Blob[]>([]);

  const backend_url = import.meta.env.VITE_BACKEND_URL;
  console.log('Backend URL:', backend_url);

  // Initialize session on component mount
  useEffect(() => {
    const initializeSession = async () => {
      try {
        setConnectionStatus('Connecting...');
        const response = await fetch(`${backend_url}/api/session/${sessionId.current}/start`);
        
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Initialize microphone recording
  const initializeRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        
        // Check if audio blob has content
        if (audioBlob.size === 0) {
          console.error('Audio blob is empty');
          alert('No audio recorded. Please try again.');
          return;
        }

        console.log(`Audio blob size: ${audioBlob.size} bytes`);
        
        // Clear the chunks for next recording
        audioChunksRef.current = [];

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

          const response = await fetch(`${backend_url}/api/chat/audio`, {
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
            const errorText = await response.text();
            console.error('Error response:', errorText);
            
            // Add error message to chat
            const errorMessage: Message = {
              text: 'Failed to process voice message. Please try again.',
              sender: 'agent',
              timestamp: new Date().toISOString(),
            };
            setMessages(prevMessages => [...prevMessages, errorMessage]);
          }
        } catch (error) {
          console.error('Error sending audio:', error);
          
          // Add error message to chat
          const errorMessage: Message = {
            text: 'Network error. Please check your connection and try again.',
            sender: 'agent',
            timestamp: new Date().toISOString(),
          };
          setMessages(prevMessages => [...prevMessages, errorMessage]);
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

      // Clear previous audio chunks and start fresh recording
      audioChunksRef.current = [];
      mediaRecorder?.start();
      setIsRecording(true);
    }
  };

  // Play audio from base64 string
  const playAudio = async (base64Audio: string) => {
    if (!base64Audio) return;

    try {
      const audio = new Audio(`data:audio/wav;base64,${base64Audio}`);
      
      // Set volume and preload
      audio.volume = 0.7;
      audio.preload = 'auto';
      
      // Handle autoplay policy by trying to play and catching the error
      const playPromise = audio.play();
      
      if (playPromise !== undefined) {
        await playPromise;
      }
    } catch (autoplayError) {
      // If autoplay fails, silently ignore - no click-to-play functionality
      console.log('Audio autoplay prevented by browser policy. Audio playback skipped.', autoplayError);
    }
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
        const response = await fetch(`${backend_url}/api/chat/text`, {
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
    <div className="min-h-screen w-full bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Header */}
      <header className="bg-white/10 backdrop-blur-sm border-b border-white/20 p-4">
        <div className="container mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar className="h-12 w-12 border-2 border-white/30">
              <AvatarImage src="/agent-jane.jpg" alt="Agent Jane" className='object-cover object-top' />
              <AvatarFallback className="bg-gradient-to-br from-purple-500 to-pink-500 text-white">
                <Bot size={24} />
              </AvatarFallback>
            </Avatar>
            <div>
              <h1 className="text-white text-lg font-semibold">Agent Jane</h1>
              <p className="text-white/70 text-sm">AI Sales Development Representative</p>
            </div>
          </div>
          
          {/* Connection Status */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              connectionStatus === 'Ready' ? 'bg-green-400 animate-pulse' :
              connectionStatus === 'Connecting...' ? 'bg-yellow-400 animate-pulse' :
              connectionStatus === 'Initializing...' ? 'bg-blue-400 animate-pulse' :
              'bg-red-400'
            }`} />
            <span className={`text-sm font-medium ${
              connectionStatus === 'Ready' ? 'text-green-300' :
              connectionStatus === 'Connecting...' ? 'text-yellow-300' :
              connectionStatus === 'Initializing...' ? 'text-blue-300' :
              'text-red-300'
            }`}>
              {connectionStatus}
            </span>
          </div>
        </div>
      </header>

      <div className="container mx-auto p-4 flex gap-6 min-h-[calc(100vh-88px)]">
        {/* Main Chat Area */}
        <div className="flex-2 flex flex-col">
          <Card className="flex-1 flex flex-col bg-white/10 backdrop-blur-sm border-white/20 shadow-2xl">
            <CardContent className="flex flex-col flex-1 p-0">
              {/* Messages Area */}
              <div ref={chatMessagesRef} className="flex-1 overflow-y-auto p-6 space-y-4">
                {messages.map((message, index) => (
                  <div key={`${message.timestamp}-${index}`} className={`flex gap-3 ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {message.sender === 'agent' && (
                      <Avatar className="h-10 w-10 border-2 border-white/30 flex-shrink-0">
                        <AvatarImage src="/agent-jane.jpg" alt="Agent Jane" className='object-cover object-top' />
                        <AvatarFallback className="bg-gradient-to-br from-purple-500 to-pink-500 text-white">
                          <Bot size={20} />
                        </AvatarFallback>
                      </Avatar>
                    )}
                    <div className={`flex flex-col max-w-[75%] ${message.sender === 'user' ? 'items-end' : 'items-start'}`}>
                      <div className={`px-4 py-3 rounded-2xl shadow-lg ${
                        message.sender === 'user' 
                          ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-br-md' 
                          : 'bg-white/80 backdrop-blur-sm border border-white/20 text-gray-800 rounded-bl-md'
                      }`}>
                        <p className="text-sm leading-relaxed">{message.text}</p>
                      </div>
                      <span className="text-xs text-white/60 mt-1 px-2">
                        {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    {message.sender === 'user' && (
                      <Avatar className="h-10 w-10 border-2 border-white/30 flex-shrink-0">
                        <AvatarFallback className="bg-gradient-to-br from-green-500 to-emerald-500 text-white">
                          <User size={20} />
                        </AvatarFallback>
                      </Avatar>
                    )}
                  </div>
                ))}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="flex gap-3">
                      <Avatar className="h-10 w-10 border-2 border-white/30">
                        <AvatarImage src="/agent-jane.jpg" alt="Agent Jane" />
                        <AvatarFallback className="bg-gradient-to-br from-purple-500 to-pink-500 text-white">
                          <Bot size={20} />
                        </AvatarFallback>
                      </Avatar>
                      <div className="bg-white/95 backdrop-blur-sm border border-white/20 px-4 py-3 rounded-2xl rounded-bl-md">
                        <div className="flex items-center gap-2">
                          <Loader2 size={16} className="animate-spin text-purple-600" />
                          <span className="text-sm text-gray-600">Agent Jane is thinking...</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
              
              {/* Input Area */}
              <div className="border-t border-white/20 bg-white/5 backdrop-blur-sm p-4">
                <div className="flex gap-3 items-end">
                  <div className="flex-1 relative">
                    <Input
                      type="text"
                      placeholder={isLoading ? "Agent Jane is processing..." : "Type your message or click the mic to speak..."}
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyPress={handleKeyPress}
                      disabled={isLoading}
                      className="pr-14 py-3 rounded-full border-2 border-white/30 bg-white/10 backdrop-blur-sm text-white placeholder:text-white/60 focus:border-blue-400 focus:bg-white/20 transition-all"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className={`absolute right-2 top-1/2 transform -translate-y-1/2 h-8 w-8 rounded-full transition-all ${
                        isRecording 
                          ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-400/50 animate-pulse' 
                          : isLoading
                            ? 'bg-gray-500/20 text-gray-400 cursor-not-allowed hover:bg-gray-500/20'
                            : 'bg-white/10 text-white/80 hover:bg-white/20 hover:text-white border border-white/30'
                      }`}
                      onClick={isLoading ? undefined : toggleRecording}
                      disabled={isLoading}
                      type='button'
                      aria-label={isRecording ? 'Stop recording' : 'Start recording'}
                    >
                      {isRecording ? <MicOff size={18} /> : <Mic size={18} />}
                    </Button>
                  </div>
                  <Button 
                    onClick={sendMessage} 
                    disabled={isLoading || !inputMessage.trim()}
                    className={`px-6 py-3 rounded-full transition-all font-medium ${
                      isLoading 
                        ? 'bg-gray-500/50 text-gray-300 cursor-not-allowed hover:bg-gray-500/50' 
                        : 'bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-lg hover:shadow-xl border-0'
                    }`}
                  >
                    {isLoading ? (
                      <>
                        <Loader2 size={18} className="mr-2 animate-spin" />
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
                  <div className="mt-3 flex items-center justify-center gap-2 text-red-300">
                    <div className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />
                    <span className="text-sm font-medium">Recording... Click mic to stop</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="w-80 flex-1 space-y-4">
          <Card className="bg-white/10 backdrop-blur-sm border-white/20 shadow-2xl">
            <CardHeader className="px-4 py-3 border-b border-white/20">
              <CardTitle className="flex items-center gap-2 text-white">
                <User size={20} className="text-blue-400" />
                Session Information
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <Tabs defaultValue="lead" className="w-full">
                <TabsList className="grid w-full grid-cols-2 mb-4 bg-white/10 border border-white/20">
                  <TabsTrigger 
                    value="lead" 
                    className="flex items-center gap-2 text-white/70 data-[state=active]:bg-white/20 data-[state=active]:text-white"
                  >
                    <User size={16} />
                    Lead Info
                  </TabsTrigger>
                  <TabsTrigger 
                    value="media" 
                    className="flex items-center gap-2 text-white/70 data-[state=active]:bg-white/20 data-[state=active]:text-white"
                  >
                    <Globe size={16} />
                    Media
                  </TabsTrigger>
                </TabsList>
                
                <TabsContent value="media" className="mt-0">
                  <div className="bg-white/5 rounded-lg border-2 border-dashed border-white/20 overflow-hidden">
                    {currentMedia ? (
                      <div className="p-4">
                        <div className="mb-3 flex items-center gap-2">
                          <Badge variant="secondary" className="text-xs bg-blue-500/20 text-blue-300 border-blue-400/30">
                            {currentMedia.type.toUpperCase()}
                          </Badge>
                          <span className="text-sm text-white/70">{currentMedia.topic}</span>
                        </div>
                        {renderMedia()}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center h-[300px] text-white/60 p-6">
                        <div className="w-16 h-16 bg-white/10 rounded-full flex items-center justify-center mb-3 border border-white/20">
                          <Globe size={24} />
                        </div>
                        <h3 className="font-medium mb-2 text-white/80">Media Display</h3>
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
                    <div className="p-4 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-lg border border-white/20 backdrop-blur-sm">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="font-medium text-white">Lead Qualification Progress</h3>
                        <Badge 
                          variant={getCompletionPercentage() === 100 ? "default" : "secondary"}
                          className={getCompletionPercentage() === 100 
                            ? "bg-green-500/20 text-green-300 border-green-400/30" 
                            : "bg-yellow-500/20 text-yellow-300 border-yellow-400/30"
                          }
                        >
                          {getCompletionPercentage()}% Complete
                        </Badge>
                      </div>
                      <Progress value={getCompletionPercentage()} className="h-2 bg-white/10" />
                      <p className="text-xs text-white/70 mt-2">
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
                      <div className="pt-4 border-t border-white/20">
                        <Button className="w-full bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white border-0">
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
