import { useState, useEffect, useCallback } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Calendar, Clock, User, Building, CheckCircle2, Loader2, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from './ui/alert';

interface BookingInfo {
  id: string;
  startTime: string;
  endTime: string;
  attendees: Array<{ email: string; name: string }>;
}

interface CalendarBookingProps {
  sessionId: string;
  leadInfo: {
    company_name: string | null;
    domain: string | null;
    problem: string | null;
    budget: string | null;
  };
  onBookingComplete: (bookingInfo: BookingInfo) => void;
  onClose: () => void;
}

interface TimeSlot {
  time: string;
  duration: number;
  available: boolean;
}

interface AvailabilityData {
  date: string;
  slots: TimeSlot[];
  timezone: string;
}

export function CalendarBooking({ sessionId, leadInfo, onBookingComplete, onClose }: CalendarBookingProps) {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [selectedTime, setSelectedTime] = useState<string>('');
  const [availability, setAvailability] = useState<AvailabilityData | null>(null);
  const [loading, setLoading] = useState(false);
  const [bookingLoading, setBookingLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');
  
  // Form fields
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: leadInfo.company_name || '',
    phone: '',
    notes: ''
  });  // Load availability when date changes
  const loadAvailability = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      
      const backend_url = import.meta.env.VITE_BACKEND_URL;
      const response = await fetch(`${backend_url}/api/calendar/availability?date=${selectedDate}`);
      
      if (response.ok) {
        const data = await response.json();
        setAvailability(data);
      } else {
        const errorData = await response.json();
        setError(errorData.error || 'Failed to load availability');
      }
    } catch {
      setError('Failed to connect to calendar service');
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => {
    loadAvailability();
  }, [loadAvailability]);
  const handleBooking = async () => {
    if (!selectedTime || !formData.name || !formData.email) {
      setError('Please fill in all required fields and select a time');
      return;
    }

    try {
      setBookingLoading(true);
      setError('');

      const backend_url = import.meta.env.VITE_BACKEND_URL;
      const bookingData = {
        session_id: sessionId,
        start_time: selectedTime,
        name: formData.name,
        email: formData.email,
        company: formData.company,
        phone: formData.phone,
        notes: formData.notes || `Meeting scheduled via Willow AI. Company: ${leadInfo.company_name}, Problem: ${leadInfo.problem}`
      };

      const response = await fetch(`${backend_url}/api/calendar/book`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(bookingData)
      });

      if (response.ok) {
        const result = await response.json();
        setSuccess(result.message);
        onBookingComplete(result);
        
        // Close modal after 2 seconds
        setTimeout(() => {
          onClose();
        }, 2000);
      } else {
        const errorData = await response.json();
        setError(errorData.error || 'Failed to book meeting');
      }
    } catch {
      setError('Failed to book meeting. Please try again.');
    } finally {
      setBookingLoading(false);
    }
  };

  const formatTimeSlot = (timeString: string) => {
    const date = new Date(timeString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const generateDateOptions = () => {
    const dates = [];
    const today = new Date();
    
    for (let i = 0; i < 14; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      dates.push(date.toISOString().split('T')[0]);
    }
    
    return dates;
  };

  const formatDateDisplay = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString([], { 
      weekday: 'long', 
      month: 'short', 
      day: 'numeric' 
    });
  };

  if (success) {
    return (
      <Card className="w-full max-w-2xl mx-auto bg-white/95 backdrop-blur-sm border border-white/20">
        <CardContent className="p-8 text-center">
          <div className="mb-4">
            <CheckCircle2 size={64} className="text-green-500 mx-auto" />
          </div>
          <h3 className="text-2xl font-semibold text-green-700 mb-2">Meeting Booked Successfully!</h3>
          <p className="text-gray-600 mb-4">{success}</p>
          <p className="text-sm text-gray-500">
            You'll receive a confirmation email shortly with all the meeting details.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-4xl mx-auto bg-white/95 backdrop-blur-sm border border-white/20">
      <CardHeader className="border-b border-white/20">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-gray-800">
            <Calendar size={24} className="text-blue-600" />
            Schedule Your Strategy Call
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </Button>
        </div>
        <p className="text-sm text-gray-600 mt-2">
          Book a 30-minute strategy call with our account executive to discuss how Willow AI can transform your lead qualification process.
        </p>
      </CardHeader>

      <CardContent className="p-6">
        {error && (
          <Alert className="mb-6 border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <AlertDescription className="text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        <div className="grid md:grid-cols-2 gap-8">
          {/* Left Column - Date & Time Selection */}
          <div>
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Calendar size={18} />
              Select Date & Time
            </h3>

            {/* Date Selection */}
            <div className="mb-6">
              <Label htmlFor="date-select" className="text-sm font-medium text-gray-700 mb-2">
                Date
              </Label>
              <select
                id="date-select"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {generateDateOptions().map(date => (
                  <option key={date} value={date}>
                    {formatDateDisplay(date)}
                  </option>
                ))}
              </select>
            </div>

            {/* Time Selection */}
            <div>
              <Label className="text-sm font-medium text-gray-700 mb-2 block">
                Available Times ({availability?.timezone || 'UTC'})
              </Label>
              
              {loading ? (
                <div className="flex items-center justify-center p-8">
                  <Loader2 size={24} className="animate-spin text-blue-600" />
                  <span className="ml-2 text-gray-600">Loading availability...</span>
                </div>
              ) : availability?.slots && availability.slots.length > 0 ? (
                <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                  {availability.slots.map((slot, index) => (
                    <Button
                      key={`${slot.time}-${index}`}
                      variant={selectedTime === slot.time ? "default" : "outline"}
                      size="sm"
                      disabled={!slot.available}
                      onClick={() => setSelectedTime(slot.time)}
                      className={`justify-center ${
                        selectedTime === slot.time 
                          ? 'bg-blue-600 text-white' 
                          : slot.available 
                            ? 'hover:bg-blue-50 hover:border-blue-300' 
                            : 'opacity-50 cursor-not-allowed'
                      }`}
                    >
                      <Clock size={14} className="mr-1" />
                      {formatTimeSlot(slot.time)}
                    </Button>
                  ))}
                </div>
              ) : (
                <div className="text-center p-8 text-gray-500">
                  <Clock size={48} className="mx-auto mb-2 opacity-50" />
                  <p>No available times for this date</p>
                  <p className="text-sm">Please select a different date</p>
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Contact Information */}
          <div>
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <User size={18} />
              Contact Information
            </h3>

            <div className="space-y-4">
              <div>
                <Label htmlFor="name" className="text-sm font-medium text-gray-700 mb-1 block">
                  Full Name *
                </Label>
                <Input
                  id="name"
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                  placeholder="Enter your full name"
                  className="w-full"
                  required
                />
              </div>

              <div>
                <Label htmlFor="email" className="text-sm font-medium text-gray-700 mb-1 block">
                  Business Email *
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({...formData, email: e.target.value})}
                  placeholder="Enter your business email"
                  className="w-full"
                  required
                />
              </div>

              <div>
                <Label htmlFor="company" className="text-sm font-medium text-gray-700 mb-1 block">
                  Company
                </Label>
                <Input
                  id="company"
                  type="text"
                  value={formData.company}
                  onChange={(e) => setFormData({...formData, company: e.target.value})}
                  placeholder="Enter your company name"
                  className="w-full"
                />
              </div>

              <div>
                <Label htmlFor="phone" className="text-sm font-medium text-gray-700 mb-1 block">
                  Phone Number
                </Label>
                <Input
                  id="phone"
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => setFormData({...formData, phone: e.target.value})}
                  placeholder="Enter your phone number"
                  className="w-full"
                />
              </div>

              <div>
                <Label htmlFor="notes" className="text-sm font-medium text-gray-700 mb-1 block">
                  Additional Notes (Optional)
                </Label>
                <Textarea
                  id="notes"
                  value={formData.notes}
                  onChange={(e) => setFormData({...formData, notes: e.target.value})}
                  placeholder="Any specific topics you'd like to discuss?"
                  className="w-full min-h-[80px]"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Lead Context Information */}
        {(leadInfo.company_name || leadInfo.problem) && (
          <div className="mt-8 p-4 bg-blue-50 rounded-lg border border-blue-200">
            <h4 className="font-medium text-blue-800 mb-2 flex items-center gap-2">
              <Building size={16} />
              Context from your conversation:
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
              {leadInfo.company_name && (
                <div>
                  <span className="font-medium text-blue-700">Company:</span>
                  <span className="text-blue-600 ml-1">{leadInfo.company_name}</span>
                </div>
              )}
              {leadInfo.problem && (
                <div>
                  <span className="font-medium text-blue-700">Challenge:</span>
                  <span className="text-blue-600 ml-1">{leadInfo.problem}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-4 mt-8 pt-6 border-t border-gray-200">
          <Button 
            variant="outline" 
            onClick={onClose}
            className="flex-1"
            disabled={bookingLoading}
          >
            Cancel
          </Button>
          <Button 
            onClick={handleBooking}
            disabled={!selectedTime || !formData.name || !formData.email || bookingLoading}
            className="flex-1 bg-blue-600 hover:bg-blue-700"
          >
            {bookingLoading ? (
              <>
                <Loader2 size={16} className="animate-spin mr-2" />
                Booking...
              </>
            ) : (
              <>
                <Calendar size={16} className="mr-2" />
                Book Meeting
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
