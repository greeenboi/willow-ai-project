import { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Calendar, User, Building, CheckCircle2, X } from 'lucide-react';

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
  onSendMessage: (message: string) => void;
}

export function CalendarBooking({ leadInfo, onClose, onSendMessage }: CalendarBookingProps) {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: leadInfo.company_name || '',
    preferredTimes: '',
    notes: ''
  });

  const handleSubmit = () => {
    // Instead of making API calls, send a message to the calendar agent
    const bookingRequest = `I'd like to schedule a meeting. Here are my details:
Name: ${formData.name}
Email: ${formData.email}
Company: ${formData.company}
Preferred times: ${formData.preferredTimes}
Additional notes: ${formData.notes}

Please help me find an available time slot and book the meeting.`;

    onSendMessage(bookingRequest);
    onClose(); // Close the modal since we're now using chat
  };

  const handleQuickBooking = (timePreference: string) => {
    const quickRequest = `I'd like to schedule a meeting ${timePreference}. My name is ${formData.name || '[Please provide name]'} and my email is ${formData.email || '[Please provide email]'}. I'm from ${leadInfo.company_name || 'my company'}.`;
    onSendMessage(quickRequest);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white/95 backdrop-blur-sm">
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-purple-600" />
            <CardTitle>Schedule a Meeting</CardTitle>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        
        <CardContent className="space-y-6">
          {/* Lead Information Display */}
          <div className="bg-purple-50 p-4 rounded-lg">
            <h3 className="font-semibold text-purple-800 mb-2 flex items-center gap-2">
              <Building className="h-4 w-4" />
              Lead Information
            </h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div><strong>Company:</strong> {leadInfo.company_name || 'Not provided'}</div>
              <div><strong>Domain:</strong> {leadInfo.domain || 'Not provided'}</div>
              <div><strong>Problem:</strong> {leadInfo.problem || 'Not provided'}</div>
              <div><strong>Budget:</strong> {leadInfo.budget || 'Not provided'}</div>
            </div>
          </div>

          {/* Quick Booking Options */}
          <div className="space-y-3">
            <h3 className="font-semibold flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              Quick Booking Options
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <Button 
                variant="outline" 
                onClick={() => handleQuickBooking('this week')}
                className="text-left justify-start"
              >
                Schedule for this week
              </Button>
              <Button 
                variant="outline" 
                onClick={() => handleQuickBooking('next week')}
                className="text-left justify-start"
              >
                Schedule for next week
              </Button>
              <Button 
                variant="outline" 
                onClick={() => handleQuickBooking('as soon as possible')}
                className="text-left justify-start"
              >
                Schedule ASAP
              </Button>
              <Button 
                variant="outline" 
                onClick={() => handleQuickBooking('at your earliest convenience')}
                className="text-left justify-start"
              >
                At your convenience
              </Button>
            </div>
          </div>

          {/* Contact Information */}
          <div className="space-y-4">
            <h3 className="font-semibold flex items-center gap-2">
              <User className="h-4 w-4" />
              Your Information
            </h3>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Your full name"
                />
              </div>
              
              <div>
                <Label htmlFor="email">Email *</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="your.email@company.com"
                />
              </div>
            </div>

            <div>
              <Label htmlFor="company">Company</Label>
              <Input
                id="company"
                value={formData.company}
                onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                placeholder="Your company name"
              />
            </div>

            <div>
              <Label htmlFor="preferredTimes">Preferred Times</Label>
              <Input
                id="preferredTimes"
                value={formData.preferredTimes}
                onChange={(e) => setFormData({ ...formData, preferredTimes: e.target.value })}
                placeholder="e.g., Monday-Friday 9AM-5PM EST, or specific dates/times"
              />
            </div>

            <div>
              <Label htmlFor="notes">Additional Notes</Label>
              <Textarea
                id="notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Any specific requirements or agenda items..."
                className="min-h-[80px]"
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row gap-3 pt-4">
            <Button 
              onClick={handleSubmit}
              className="flex-1 bg-purple-600 hover:bg-purple-700"
              disabled={!formData.name || !formData.email}
            >
              <CheckCircle2 className="h-4 w-4 mr-2" />
              Request Meeting via Chat
            </Button>
            <Button variant="outline" onClick={onClose} className="flex-1">
              Cancel
            </Button>
          </div>

          <div className="text-sm text-gray-600 text-center">
            Our calendar assistant will help you find the perfect time slot through the chat interface.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}