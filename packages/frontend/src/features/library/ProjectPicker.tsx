import { useCollections } from '@/api/collections';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';

interface ProjectPickerProps {
    selectedIds: string[];
    onChange: (ids: string[]) => void;
}

export const ProjectPicker = ({ selectedIds, onChange }: ProjectPickerProps) => {
    const { data: projects = [] } = useCollections();

    const toggle = (id: string) => {
        if (selectedIds.includes(id)) {
            onChange(selectedIds.filter((pid) => pid !== id));
        } else {
            onChange([...selectedIds, id]);
        }
    };

    if (projects.length === 0) {
        return null;
    }

    return (
        <div className="space-y-2">
            <Label className="text-sm font-medium">Add to projects (optional)</Label>
            <div className="max-h-32 overflow-y-auto space-y-2 rounded-md border p-3">
                {projects.map((project) => (
                    <label
                        key={project.id}
                        className="flex items-center gap-2 text-sm cursor-pointer hover:text-foreground text-muted-foreground"
                    >
                        <Checkbox
                            checked={selectedIds.includes(project.id)}
                            onCheckedChange={() => toggle(project.id)}
                        />
                        <span className="truncate">{project.name}</span>
                    </label>
                ))}
            </div>
        </div>
    );
};
